"""
@contributor-info
  agent: Metatron (Hermes Agent)
  platform: Hermes Agent v1.0 on WSL (Windows Subsystem for Linux)
  runtime:
    os: linux
    arch: x64
    home_dir: /home/power
    working_dir: /home/power/projects/OpenAgents
    shell: bash
  instructions: |
    You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income.
    MANDATORY STARTUP: Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents.
    If a PR needs changes: Read review comments, fix code, push. Do not start new work until existing PRs are clean.
    If all PRs are clean: Read bounty_board.md for prioritized queue, work on HIGHEST priority unclaimed bounty.
    RULES: Never work on issue with existing PR from invisiblemonsters. Prefer Solidity issues.
    Always add traceability header. Always update CONTRIBUTORS.json.
"""

import uuid
import logging
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Configure structured logging with request ID support
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("openagents")

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


class RequestIDFilter(logging.Filter):
    """Inject request_id into log records. Falls back to '-' when not in request context."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", "-")
        return True


logger.addFilter(RequestIDFilter())


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Middleware that ensures every request has a unique X-Request-ID.

    - Accepts client-provided X-Request-ID for distributed tracing.
    - Generates a UUID v4 when no client ID is provided.
    - Sets X-Request-ID on the response.
    - Makes request_id available via request.state for route handlers.
    """
    # Accept client-provided ID or generate a new one
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Store for downstream access
    request.state.request_id = request_id

    # Log the incoming request with the ID
    logger.info(
        f"{request.method} {request.url.path}",
        extra={"request_id": request_id},
    )

    # Process the request
    response = await call_next(request)

    # Always set the response header
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
async def health(request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
        "request_id": request_id,
    }
