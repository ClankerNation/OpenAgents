from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
import logging

from api.routes.ws_manager import manager
from api.middleware.auth import decode_token

logger = logging.getLogger("openagents.main")

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


@app.websocket("/tasks/ws/tasks")
async def task_updates_ws(websocket: WebSocket, token: str = ""):
    """
    WebSocket endpoint for real-time task status updates.

    Query parameters:
      - token: JWT access token for authentication.

    Protocol:
      1. Client connects with ?token=<jwt>
      2. Server validates token and sends {"type": "connected", ...} welcome
      3. Client may send {"type": "ping"} → server replies {"type": "pong"}
      4. Server pushes task status changes as {"type": "task_update", ...}
      5. Connection drops → manager.disconnect() is called
    """
    # -- Authenticate via query-param token --
    if not token:
        logger.warning("WebSocket rejected: no token provided")
        await websocket.close(code=4001)
        return

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("WebSocket rejected: no 'sub' in token")
            await websocket.close(code=4001)
            return
    except HTTPException:
        await websocket.close(code=4001)
        return
    except Exception:
        logger.exception("WebSocket auth error")
        await websocket.close(code=4001)
        return

    # -- Accept connection --
    await manager.connect(websocket, user_id)

    try:
        # Send welcome message
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "user_id": user_id,
                    "message": "Connected to task updates",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        )

        # Main message loop — supports ping/pong keepalive
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected (client): user=%s", user_id)
    except Exception:
        logger.exception("WebSocket error: user=%s", user_id)
    finally:
        manager.disconnect(websocket)
