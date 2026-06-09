"""
@contributor-info
  identity: Qwen Code 0.14.0 (AIGON Enterprise agent)
  os: Linux 5.15.0 x86_64
  home: /root
  working-dir: /tmp/OpenAgents
  session-dir: /opt/projects/kraina
  shell: /bin/bash
  context: |
    Full system prompt context (truncated for size).
    AIGON Enterprise WAR MODE - Qwen executes under AIGON Brain orchestration.
    Key directives: parallel execution (Iron Law #2), no impossible (Iron Law #3),
    AIGON Brain first, 20 quality gates mandatory, no curl, no hardcoded data.
    Output language: English. Operating under System Law Omega (L1-L11 + C1-C8).
"""

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.security import HTTPBearer, APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# OpenAPI Security Schemes
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(
    scheme_name="JWT Bearer",
    description="Standard JWT bearer token obtained via /auth/login endpoint",
    auto_error=False,
)

api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    scheme_name="API Key",
    description="Premium API key for higher rate limits. Obtain from dashboard.",
    auto_error=False,
)


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol. "
    "All endpoints returning agent/task data are public. "
    "Mutating endpoints (POST, PUT, PATCH, DELETE) require authentication. "
    "Two auth methods are supported: JWT Bearer token (standard) and X-API-Key header (premium).",
    version="0.1.0",
    openapi_tags=[
        {"name": "agents", "description": "Agent registry operations"},
        {"name": "tasks", "description": "Task and bounty management"},
        {"name": "leaderboard", "description": "Reputation leaderboard"},
        {"name": "health", "description": "Service health check"},
    ],
)

# Security scheme definitions for OpenAPI
SECURITY_SCHEMES = {
    "JWT Bearer": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Standard JWT bearer token. Obtain via /auth/login with wallet signature.",
    },
    "API Key": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Premium API key for elevated rate limits. Obtain from your dashboard.",
    },
}


# ---------------------------------------------------------------------------
# Error response schemas
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standard error response body."""
    error: str = Field(..., description="Error message describing what went wrong")
    detail: Optional[str] = Field(None, description="Additional error details when available")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"error": "Agent not found"},
                {"error": "Not authenticated", "detail": "Missing or invalid token"},
                {"error": "Rate limit exceeded", "detail": "60 requests per minute allowed"},
            ]
        }
    }


# Named error response schemas for documentation
ERROR_400 = {"model": ErrorResponse, "description": "Bad request -- invalid parameters or body"}
ERROR_401 = {"model": ErrorResponse, "description": "Unauthorized -- missing or invalid authentication"}
ERROR_403 = {"model": ErrorResponse, "description": "Forbidden -- insufficient permissions"}
ERROR_404 = {"model": ErrorResponse, "description": "Resource not found"}
ERROR_429 = {"model": ErrorResponse, "description": "Rate limit exceeded -- retry after Retry-After header"}


# ---------------------------------------------------------------------------
# Pydantic models with examples
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    """Agent metadata returned by the API."""
    agent_id: str = Field(..., description="Unique agent identifier (on-chain address)")
    name: str = Field(..., description="Human-readable agent name", examples=["AlphaOracle"])
    owner: str = Field(
        ..., description="Owner wallet address",
        examples=["0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"],
    )
    endpoint: str = Field(
        ..., description="Agent service endpoint URL",
        examples=["https://agent.example.com/api"],
    )
    reputation: int = Field(..., ge=0, description="Cumulative reputation score", examples=[142])
    tasks_completed: int = Field(..., ge=0, description="Completed tasks count", examples=[37])
    registered_at: datetime = Field(..., description="Registration timestamp")
    active: bool = Field(..., description="Whether the agent is accepting tasks", examples=[True])

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "agent_id": "0x1234...abcd",
                "name": "AlphaOracle",
                "owner": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
                "endpoint": "https://agent.example.com/api",
                "reputation": 142,
                "tasks_completed": 37,
                "registered_at": "2026-01-15T10:30:00Z",
                "active": True,
            }]
        }
    }


class TaskResponse(BaseModel):
    """Bounty task details."""
    task_id: int = Field(..., description="Unique task identifier")
    creator: str = Field(..., description="Task creator wallet address")
    description: str = Field(..., description="Task description and requirements")
    reward_wei: str = Field(
        ..., description="Reward in wei (string avoids precision loss)",
        examples=["1000000000000000000"],
    )
    deadline: datetime = Field(..., description="Submission deadline")
    status: str = Field(..., description="Task status", examples=["open"])
    assigned_agent: Optional[str] = Field(None, description="Assigned agent, if any")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "task_id": 42,
                "creator": "0x1234...abcd",
                "description": "Implement OpenAPI schema generation",
                "reward_wei": "1000000000000000000",
                "deadline": "2026-07-01T00:00:00Z",
                "status": "open",
                "assigned_agent": None,
            }]
        }
    }


class LeaderboardEntry(BaseModel):
    """Agent ranking entry."""
    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")
    reputation: int = Field(..., ge=0, description="Total reputation score")
    tasks_completed: int = Field(..., ge=0, description="Total completed tasks")
    success_rate: float = Field(
        ..., ge=0.0, le=1.0,
        description="Fraction of completed tasks over total assignments",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "agent_id": "0x1234...abcd",
                "name": "AlphaOracle",
                "reputation": 142,
                "tasks_completed": 37,
                "success_rate": 0.95,
            }]
        }
    }


# ---------------------------------------------------------------------------
# In-memory store (placeholder for database)
# ---------------------------------------------------------------------------

agents_cache: dict = {}
tasks_cache: dict = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    summary="List all registered agents",
    description="Returns a paginated list of agents, optionally filtered by activity and minimum reputation.",
    responses={200: {"description": "List of agents"}, 400: ERROR_400},
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to only active agents"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    tags=["agents"],
    summary="Get agent by ID",
    description="Returns detailed information for a single agent by its on-chain identifier.",
    responses={200: {"description": "Agent details"}, 404: ERROR_404},
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    tags=["tasks"],
    summary="List all bounty tasks",
    description="Returns a paginated list of bounty tasks, optionally filtered by status.",
    responses={200: {"description": "List of tasks"}, 400: ERROR_400},
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["tasks"],
    summary="Get task by ID",
    description="Returns detailed information for a single bounty task.",
    responses={200: {"description": "Task details"}, 404: ERROR_404},
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    tags=["leaderboard"],
    summary="Get agent reputation leaderboard",
    description="Returns the top agents ranked by reputation score.",
    responses={200: {"description": "Leaderboard sorted by reputation (descending)"}},
)
async def leaderboard(limit: int = Query(20, le=50, description="Maximum leaderboard entries")):
    entries = []
    for agent in agents_cache.values():
        completed = agent.get("tasks_completed", 0)
        entries.append({
            "agent_id": agent["agent_id"],
            "name": agent["name"],
            "reputation": agent.get("reputation", 0),
            "tasks_completed": completed,
            "success_rate": completed / max(completed + 1, 1),
        })
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]


@app.get(
    "/health",
    tags=["health"],
    summary="Service health check",
    description="Returns the service health status including indexed counts.",
    responses={200: {"description": "Service is healthy"}},
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Custom OpenAPI schema generator with security schemes
# ---------------------------------------------------------------------------

_original_openapi = app.openapi


def _custom_openapi():
    """Generate OpenAPI schema with security schemes registered."""
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = _original_openapi()
    if schema is None:
        schema = {}

    # Inject security schemes into components
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = SECURITY_SCHEMES

    # Apply security to mutating endpoints (POST, PUT, PATCH, DELETE)
    for path, methods in schema.get("paths", {}).items():
        for method, detail in methods.items():
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                detail.setdefault("security", [])
                detail["security"].append({"JWT Bearer": []})
                detail["security"].append({"API Key": []})

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
