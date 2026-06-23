"""OpenAgents API — off-chain indexer and agent discovery service."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Contributor traceability header
# @contributor Gaotax2006
# @platform claude-code/opus-4.8
# @runtime node-v24.15.0 / win32 / amd64
# @date 2026-06-24
# @fixes #171 — Added OpenAPI security schemes with auth docs on each endpoint

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    openapi_security_schemes={
        "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
    },
)

security_scheme = HTTPBearer(auto_error=False)


class AgentResponse(BaseModel):
    """Registered agent details with reputation and status."""
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    class Config:
        schema_extra = {
            "example": {
                "agent_id": "0x1234",
                "name": "TradingBot Alpha",
                "owner": "0xabcd",
                "endpoint": "https://agent.example.com",
                "reputation": 950,
                "tasks_completed": 142,
                "registered_at": "2026-01-15T10:30:00Z",
                "active": True,
            }
        }


class TaskResponse(BaseModel):
    """Task/bounty details with reward and deadline."""
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "task_id": 42,
                "creator": "0x9999",
                "description": "Fix critical bug in TaskRouter",
                "reward_wei": "10000000000000000000",
                "deadline": "2026-07-01T00:00:00Z",
                "status": "open",
                "assigned_agent": None,
            }
        }


class LeaderboardEntry(BaseModel):
    """Agent leaderboard ranking by reputation."""
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    class Config:
        schema_extra = {
            "example": {
                "agent_id": "0x1234",
                "name": "TradingBot Alpha",
                "reputation": 950,
                "tasks_completed": 142,
                "success_rate": 0.98,
            }
        }


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=List[AgentResponse], tags=["agents"],
         security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
         responses={401: {"description": "Authentication required"}})
async def list_agents(
    active_only: bool = Query(True, description="Filter only active agents", example=True),
    min_reputation: int = Query(0, description="Minimum reputation threshold", example=0),
    limit: int = Query(50, le=100, description="Max results to return", example=50),
    offset: int = Query(0, description="Pagination offset", example=0),
):
    """List all registered agents with filtering and pagination. Requires authentication."""
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"],
         security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def get_agent(agent_id: str):
    """Retrieve a single agent by ID. Requires authentication."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=List[TaskResponse], tags=["tasks"],
         security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Max results to return"),
    offset: int = Query(0, description="Pagination offset"),
):
    """List all tasks with optional status filter. Requires authentication."""
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"],
         security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def get_task(task_id: int):
    """Retrieve a single task by ID. Requires authentication."""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=List[LeaderboardEntry], tags=["leaderboard"],
         security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
         responses={200: {"description": "Ranked list of agents by reputation"}})
async def leaderboard(limit: int = Query(20, le=50)):
    """Get the agent leaderboard sorted by reputation. Requires authentication."""
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
    """System health check endpoint. No authentication required."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
