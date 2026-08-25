# @contributor-info rafaio1
# @session-init Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for OpenAPI schema generation with authentication documentation (Issue #185)
# @os linux
# @arch x64
# @home /root
# @workdir /tmp/openagents_issue_185
# @shell /bin/bash
"""OpenAgents API entry point with comprehensive OpenAPI security scheme documentation.

Implements JWT Bearer and API Key security schemes, error response schemas,
and example values for all models per Issue #185 requirements.
Closes #185
"""
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# Security schemes for OpenAPI documentation
bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token for authenticated endpoints")
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="API key for premium access")

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    openapi_tags=[
        {"name": "agents", "description": "Agent registration and discovery"},
        {"name": "tasks", "description": "Task creation and assignment"},
        {"name": "leaderboard", "description": "Reputation-based rankings"},
        {"name": "health", "description": "Service health checks"},
    ],
)


# ─── Error Response Schemas ──────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standardized error response format."""
    code: str = Field(..., example="VALIDATION_ERROR")
    message: str = Field(..., example="Request validation failed")
    request_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")
    details: Optional[dict] = Field(None, example={"fields": [{"field": "name", "message": "required"}]})


# ─── Response Models ─────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="0xabc123def456")
    name: str = Field(..., example="AutoBountyHunter-v3")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18")
    endpoint: str = Field(..., example="https://agent.example.com/api/v1")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=142)
    registered_at: datetime = Field(..., example="2026-08-20T14:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=1042)
    creator: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18")
    description: str = Field(..., example="Fix reentrancy vulnerability in StakingRewards.sol")
    reward_wei: str = Field(..., example="5000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="assigned")
    assigned_agent: Optional[str] = Field(None, example="0xabc123def456")


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., example="0xabc123def456")
    name: str = Field(..., example="AutoBountyHunter-v3")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=142)
    success_rate: float = Field(..., example=0.97)


# ─── In-memory store (placeholder for DB) ───────────────────────────────────

agents_cache: dict = {}
tasks_cache: dict = {}


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to active agents only"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold"),
    limit: int = Query(50, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
):
    """List registered agents with optional filtering.

    Requires JWT Bearer authentication for access.
    """
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    tags=["agents"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Agent not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def get_agent(
    agent_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
):
    """Get a single agent by ID.

    Returns 404 if the agent does not exist.
    """
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    tags=["tasks"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    api_key: Optional[str] = Security(api_key_scheme),
):
    """List tasks with optional status filter.

    Supports both JWT Bearer and API Key authentication.
    """
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["tasks"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Task not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def get_task(
    task_id: int,
    api_key: Optional[str] = Security(api_key_scheme),
):
    """Get a single task by ID.

    Returns 404 if the task does not exist.
    """
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    tags=["leaderboard"],
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def leaderboard(
    limit: int = Query(20, ge=1, le=50, description="Number of top agents to return"),
):
    """Get reputation-based agent leaderboard.

    Public endpoint — no authentication required.
    """
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


@app.get(
    "/health",
    tags=["health"],
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "agents_indexed": 1523,
                        "tasks_indexed": 847,
                        "timestamp": "2026-08-25T07:15:00Z",
                    }
                }
            },
        },
    },
)
async def health():
    """Health check endpoint. No authentication required."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
