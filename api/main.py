
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from typing import Optional, Set
from datetime import datetime
import asyncio
import json

from .models.database import get_db, AuditLog
from .middleware.auth import get_current_user

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

connected_websockets: Set[WebSocket] = set()


@app.websocket("/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    subscribed = set()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "subscribe" and msg.get("task_id"):
                subscribed.add(msg["task_id"])
                await websocket.send_json({"type": "subscribed", "task_id": msg["task_id"]})
            elif msg.get("type") == "unsubscribe" and msg.get("task_id"):
                subscribed.discard(msg["task_id"])
                await websocket.send_json({"type": "unsubscribed", "task_id": msg["task_id"]})
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)


async def broadcast_task_update(task_id: int, status: str):
    message = json.dumps({"type": "task_update", "task_id": task_id, "status": status})
    dead = set()
    for ws in connected_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    connected_websockets -= dead


@app.on_event("startup")
async def startup():
    asyncio.create_task(heartbeat_loop())


async def heartbeat_loop():
    while True:
        await asyncio.sleep(30)
        dead = set()
        for ws in connected_websockets:
            try:
                await ws.send_json({"type": "heartbeat"})
            except Exception:
                dead.add(ws)
        connected_websockets -= dead


@app.get("/admin/audit-log")
async def get_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        query = query.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to))
    query = query.order_by(AuditLog.timestamp.desc())
    total = query.count()
    results = query.offset(skip).limit(limit).all()
    return {"total": total, "skip": skip, "limit": limit, "logs": [r.to_dict() for r in results]}
