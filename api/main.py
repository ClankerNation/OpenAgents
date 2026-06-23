from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Set
from datetime import datetime
import asyncio

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    entries = []
    for agent in agents_cache.values():
        completed = agent.get("tasks_completed", 0)
        entries.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "reputation": agent.get("reputation", 0),
                "tasks_completed": completed,
                "success_rate": completed / max(completed + 1, 1),
            }
        )
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }


# WebSocket store: {client_id: {"tasks": set(task_ids)}}
_active_connections: Dict[str, dict] = {}


async def broadcast_task_update(task_id: int, update_data: dict):
    """Broadcast a task update to all connected WebSocket clients subscribed to that task."""
    dead_clients = []
    for client_id, conn in _active_connections.items():
        if task_id in conn["tasks"]:
            try:
                await conn["websocket"].send_json({"type": "task_update", "task_id": task_id, **update_data})
            except Exception:
                dead_clients.append(client_id)
    # Clean up dead connections
    for cid in dead_clients:
        _active_connections.pop(cid, None)


@app.websocket("/tasks/ws")
async def websocket_task_updates(websocket: WebSocket):
    """WebSocket endpoint for real-time task status updates.

    Clients connect via ws://host/tasks/ws and can subscribe to specific
    task IDs using JSON messages. Task status changes are broadcast
    to all subscribed clients in real time.

    ## Protocol
    - Subscribe:  {"type":"subscribe","task_id":123}
    - Unsubscribe: {"type":"unsubscribe","task_id":123}
    - Updates:    {"type":"task_update","task_id":123,"status":"completed",...}
    - Pings:      {"type":"ping","timestamp":"..."} (every 30s)
    """
    await websocket.accept()
    client_id = str(id(websocket))
    _active_connections[client_id] = {"tasks": set(), "websocket": websocket}

    try:
        while True:
            data = await websocket.receive_text()
            msg = None
            try:
                import json
                msg = json.loads(data)
            except Exception:
                pass

            if msg and msg.get("type") == "subscribe":
                _active_connections[client_id]["tasks"].add(msg["task_id"])
                await websocket.send_text('{"type":"subscribed","task_id":' + str(msg["task_id"]) + '}')
            elif msg and msg.get("type") == "unsubscribe":
                _active_connections[client_id]["tasks"].discard(msg["task_id"])
                await websocket.send_text('{"type":"unsubscribed","task_id":' + str(msg["task_id"]) + '}')
            else:
                # Send heartbeat ping every 30 seconds if no message received
                await websocket.send_text('{"type":"ping","timestamp":"' + datetime.utcnow().isoformat() + '"}')
                await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        _active_connections.pop(client_id, None)


@app.on_event("shutdown")
async def cleanup_websockets():
    """Clean up all WebSocket connections on shutdown."""
    for client_id in list(_active_connections.keys()):
        conn = _active_connections[client_id]
        ws = conn.get("websocket")
        if ws:
            await ws.close()
    _active_connections.clear()
