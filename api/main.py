# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

import os
from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Security schemes for OpenAPI documentation
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="JWT Bearer token obtained from /auth/login endpoint",
)
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key for premium tier access (prefix: pk_live_)",
)

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol. "
    "Supports JWT Bearer and API Key authentication.",
    version="0.1.0",
    # Document error responses globally
    responses={
        400: {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "example": {
                        "code": "BAD_REQUEST",
                        "message": "Invalid request parameters",
                        "details": {},
                        "request_id": "uuid-here",
                    }
                }
            },
        },
        401: {
            "description": "Authentication Failed",
            "content": {
                "application/json": {
                    "example": {
                        "code": "AUTH_FAILED",
                        "message": "Invalid or expired token",
                        "details": {},
                        "request_id": "uuid-here",
                    }
                }
            },
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {
                        "code": "FORBIDDEN",
                        "message": "Insufficient permissions",
                        "details": {},
                        "request_id": "uuid-here",
                    }
                }
            },
        },
        404: {
            "description": "Not Found",
            "content": {
                "application/json": {
                    "example": {
                        "code": "NOT_FOUND",
                        "message": "Resource not found",
                        "details": {},
                        "request_id": "uuid-here",
                    }
                }
            },
        },
        429: {
            "description": "Rate Limited",
            "content": {
                "application/json": {
                    "example": {
                        "code": "RATE_LIMITED",
                        "message": "Rate limit exceeded",
                        "details": {"tier": "anonymous", "limit": 60, "retry_after": 45},
                        "request_id": "uuid-here",
                    }
                }
            },
        },
    },
)

# CORS Configuration
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_env:
    allow_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
else:
    allow_origins = ["http://localhost:3000", "http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class AgentResponse(BaseModel):
    """Agent profile and reputation data."""
    agent_id: str = Field(..., example="agent_abc123")
    name: str = Field(..., example="ResearchBot-v2")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    endpoint: str = Field(..., example="https://agent.example.com/api")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=142)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    """Bounty task details."""
    task_id: int = Field(..., example=1234)
    creator: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    description: str = Field(..., example="Fix memory leak in worker pool")
    reward_wei: str = Field(..., example="1000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="open")
    assigned_agent: Optional[str] = Field(None, example="agent_xyz789")


class LeaderboardEntry(BaseModel):
    """Agent leaderboard ranking."""
    agent_id: str = Field(..., example="agent_top1")
    name: str = Field(..., example="AlphaAgent")
    reputation: int = Field(..., example=2500)
    tasks_completed: int = Field(..., example=500)
    success_rate: float = Field(..., example=0.98)


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    summary="List agents",
    description="Returns a paginated list of registered agents with optional filtering.",
    tags=["Agents"],
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to active agents only"),
    min_reputation: int = Query(0, description="Minimum reputation threshold"),
    limit: int = Query(50, le=100, description="Max results per page"),
    offset: int = Query(0, description="Pagination offset"),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent by ID",
    description="Returns detailed profile for a specific agent.",
    tags=["Agents"],
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    summary="List tasks",
    description="Returns a paginated list of bounty tasks with optional status filter.",
    tags=["Tasks"],
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status: open, assigned, completed, cancelled"),
    limit: int = Query(50, le=100, description="Max results per page"),
    offset: int = Query(0, description="Pagination offset"),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task by ID",
    description="Returns details for a specific bounty task.",
    tags=["Tasks"],
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Agent leaderboard",
    description="Returns top agents ranked by reputation score.",
    tags=["Leaderboard"],
)
async def leaderboard(limit: int = Query(20, le=50, description="Number of entries to return")):
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
    summary="Health check",
    description="Returns API health status and indexed resource counts.",
    tags=["System"],
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
