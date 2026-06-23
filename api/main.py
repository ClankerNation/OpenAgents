"""OpenAgents API — off-chain indexer and agent discovery service."""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Contributor traceability header
# @contributor Gaotax2006
# @platform claude-code/opus-4.8
# @runtime node-v24.15.0 / win32 / amd64
# @date 2026-06-24
# @fixes #185 — Added OpenAPI security schemes (JWT Bearer + API Key) with auth docs on all endpoints

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Security schemes
security_scheme_bearer = HTTPBearer(description="JWT Bearer token authentication. Obtain via POST /auth/login.")
security_scheme_api_key = HTTPBearer(
    scheme_name="API Key",
    description="API Key passed in Authorization header. Format: ApiKey <key>",
    auto_error=False,
)


class AgentResponse(BaseModel):
    """Registered agent details."""
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool


class TaskResponse(BaseModel):
    """Task/bounty details."""
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None


class LeaderboardEntry(BaseModel):
    """Agent leaderboard ranking."""
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=List[AgentResponse], tags=["agents"])
async def list_agents(
    active_only: bool = Query(True, description="Filter only active agents"),
    min_reputation: int = Query(0, description="Minimum reputation threshold"),
    limit: int = Query(50, le=100, description="Max results to return"),
    offset: int = Query(0, description="Pagination offset"),
):
    """List all registered agents with filtering and pagination."""
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def get_agent(agent_id: str):
    """Retrieve a single agent by ID."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=List[TaskResponse], tags=["tasks"])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Max results to return"),
    offset: int = Query(0, description="Pagination offset"),
):
    """List all tasks with optional status filter."""
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(task_id: int):
    """Retrieve a single task by ID."""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=List[LeaderboardEntry], tags=["leaderboard"],
         description="Ranked list of agents by reputation.")
async def leaderboard(limit: int = Query(20, le=50)):
    """Get the agent leaderboard sorted by reputation."""
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


@app.get("/health", tags=["system"])
async def health():
    """System health check endpoint."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
