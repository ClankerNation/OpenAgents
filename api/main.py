# @contributor-info rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import uuid
import logging
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

logger = logging.getLogger("openagents")


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


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # Accept client-provided X-Request-ID for distributed tracing, else generate UUID
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    request: Request = None,
):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    logger.info(f"[{request_id}] list_agents called active_only={active_only} min_rep={min_reputation}")
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, request: Request = None):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    if agent_id not in agents_cache:
        logger.warning(f"[{request_id}] Agent not found: {agent_id}")
        raise HTTPException(status_code=404, detail="Agent not found")
    logger.info(f"[{request_id}] get_agent {agent_id}")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    request: Request = None,
):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    logger.info(f"[{request_id}] list_tasks status={status}")
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, request: Request = None):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    if task_id not in tasks_cache:
        logger.warning(f"[{request_id}] Task not found: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"[{request_id}] get_task {task_id}")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50), request: Request = None):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    logger.info(f"[{request_id}] leaderboard limit={limit}")
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
async def health(request: Request = None):
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"
    logger.info(f"[{request_id}] health check")
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
