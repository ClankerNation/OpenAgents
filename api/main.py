# Contributor Metadata
# Agent Name: Codex (GPT-5)
# Platform Initialization: Codex desktop session initialization context (system/developer/runtime directives) active for this task.
# Runtime Environment: Microsoft Windows 11 Home China Edition, 64-bit
# Working Directory: F:\jiedan\OpenAgents-178
# Shell: powershell

import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        return True


def _configure_request_id_logging() -> None:
    request_id_filter = RequestIdFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(request_id_filter)
    for handler in root_logger.handlers:
        handler.addFilter(request_id_filter)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        named_logger = logging.getLogger(logger_name)
        named_logger.addFilter(request_id_filter)
        for handler in named_logger.handlers:
            handler.addFilter(request_id_filter)

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

_configure_request_id_logging()
logger = logging.getLogger("openagents.api")


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx_var.set(request_id)
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    finally:
        request_id_ctx_var.reset(token)

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request completed request_id=%s method=%s path=%s status=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
    )
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
