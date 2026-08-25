# @fix-author rafaio1
# @date 2026-08-25T05:30:00Z
# @runtime linux x64 /tmp/openagents_issue_202 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for structured error responses (Issue #202)
"""OpenAgents API entry point with structured error handling and request ID correlation.

Closes #202
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError

from .errors import (
    ApiError,
    ErrorCode,
    NotFoundError,
    api_error_handler,
    build_error_response,
    http_exception_handler,
    validation_error_handler,
)

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Register structured error handlers
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(ValidationError, validation_error_handler)
app.add_exception_handler(Exception, http_exception_handler)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Inject a unique request ID into every request/response cycle."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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
        raise NotFoundError(resource="Agent", identifier=agent_id)
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
        raise NotFoundError(resource="Task", identifier=task_id)
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
