# @contributor: hermes-agent
# @platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
# @env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
# @timestamp: 2026-05-18

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Request ID Middleware for Log Correlation
# ---------------------------------------------------------------------------
# Each request gets a unique UUID request ID. If the client sends an
# X-Request-ID header, that value is accepted for distributed tracing.
# The request ID is attached to every log message via a ContextVar-aware
# filter so that structured log correlation works across every handler.
# ---------------------------------------------------------------------------

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("")  # type: ignore[attr-defined]
        return True


# Configure structured logging with request ID
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s | %(levelname)-8s | request_id=%(request_id)s | %(name)s | %(message)s"
    )
)
_handler.addFilter(RequestIdFilter())

_logger = logging.getLogger("openagents")
_logger.setLevel(logging.INFO)
_logger.addHandler(_handler)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Generate or accept a request ID for every HTTP request.

    * If the client supplies ``X-Request-ID`` it is used (distributed tracing).
    * Otherwise a new UUID4 is generated.
    * The resolved ID is stored in a ``ContextVar`` so log messages emitted
      anywhere in the request lifecycle automatically carry it.
    * The ID is always returned in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next):
        # Accept client-provided ID or generate a new one
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_ctx.set(request_id)

        _logger.info("Request started %s %s", request.method, request.url.path)

        response: Response = await call_next(request)

        response.headers["X-Request-ID"] = request_id

        _logger.info("Request finished %s %s → %s", request.method, request.url.path, response.status_code)

        return response


app.add_middleware(RequestIdMiddleware)


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
_ENV_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")

if _ENV_ORIGINS.strip():
    _allowed_origins: list[str] = [
        origin.strip() for origin in _ENV_ORIGINS.split(",") if origin.strip()
    ]
else:
    _allowed_origins = ["http://localhost:3000", "http://localhost:8000"]

_allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
_allowed_headers = ["Authorization", "Content-Type", "Accept", "X-Request-ID"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=_allowed_methods,
    allow_headers=_allowed_headers,
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