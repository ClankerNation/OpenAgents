"""OpenAgents API — Decentralized AI Agent Orchestration Protocol.

@fix-author
  name: Hermes Agent (dev-nana27)
  date: 2026-07-04
  pre_session_preamble: |
    You are Hermes Agent Bot, an autonomous AI agent operating a solo
    AI-venture company. Your mission is to find and execute high-value
    bounty tasks on GitHub. You operate on a ¥100 token budget with
    7-day survival window.
  runtime:
    os: linux
    arch: x64 (WSL2 on Windows)
    working_dir: /tmp/OpenAgents
    shell: bash
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from .middleware.auth import get_current_user
from .middleware.ratelimit import RateLimitMiddleware, RateLimitConfig
from .routes import tasks, agents, payments
from .routes.auth import router as auth_router
from .models.database import init_db

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Initialize database tables on startup
init_db()

# Register route modules
app.include_router(auth_router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(payments.router)


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
    user: dict = Depends(get_current_user),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user: dict = Depends(get_current_user),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    user: dict = Depends(get_current_user),
):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    limit: int = Query(20, le=50),
    user: dict = Depends(get_current_user),
):
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


# Add rate limiter with differentiated limits
app.add_middleware(
    RateLimitMiddleware,
    config=RateLimitConfig(
        requests_per_window=200,  # Default higher for API key users
        window_seconds=60,
        burst_limit=30,
    ),
)
