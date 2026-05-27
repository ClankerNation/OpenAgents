"""
@fix-author
Name: Karry2019web (Hermes Autonomous Agent)
Date: 2026-05-27
Session initialization: This agent is running as a scheduled cron job on Windows 10 (git-bash) 
via Hermes Agent. Model: deepseek-chat via deepseek provider.
Objective: Integrate structured error responses for bounty #202 ($8600).
@runtime
os: Windows 10
arch: x86_64
working_dir: C:\Users\Administrator\AppData\Local\hermes\hermes-agent
shell: git-bash (MSYS)
---

Main FastAPI application for the OpenAgents protocol off-chain indexer.
"""

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import time as time_mod

from api.errors import register_error_handlers, ErrorCode

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


@app.middleware("http")
async def set_start_time(request: Request, call_next):
    request.scope["start_time"] = time_mod.time()
    return await call_next(request)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    elapsed_ms = int((time_mod.time() - request.scope.get("start_time", 0)) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    return response


register_error_handlers(app)


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


agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(active_only: bool = Query(True), min_reputation: int = Query(0), limit: int = Query(50, le=100), offset: int = Query(0)):
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
async def list_tasks(status: Optional[str] = Query(None), limit: int = Query(50, le=100), offset: int = Query(0)):
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
        entries.append({
            "agent_id": agent["agent_id"], "name": agent["name"],
            "reputation": agent.get("reputation", 0), "tasks_completed": completed,
            "success_rate": completed / max(completed + 1, 1),
        })
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]


@app.get("/health")
async def health():
    return {
        "status": "ok", "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
