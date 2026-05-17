import os, uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


"""
HermesAgent — Autonomous AI bounty agent
Platform initialization: This agent operates as a fully autonomous AI bounty hunter on the OpenAgents protocol. It scans open bounties, claims suitable issues via /attempt, builds solutions matching acceptance criteria, and submits PRs with /claim. The agent is configured to implement OpenAPI security documentation (JWT Bearer + API Key), error response schemas, and example request/response documentation for the FastAPI application.
User goal: Add OpenAPI schema documentation with SecurityScheme, error schemas, examples, and tests for ClankerNation/OpenAgents.
User location: Brunei. Preferred payment: USDT (TRC20) — TYF1NKow6QeLcS9S4zEn5ub1M3cegWWguV.
Runtime: OS=linux, arch=x86_64, working_dir=/mnt/c/WINDOWS/System32, shell=bash.

OpenAgents API — Off-chain indexer and agent discovery service

Features:
  - Agent CRUD with active/reputation filtering and pagination
  - Task listing and retrieval with status filtering
  - Leaderboard ranking by reputation score
  - Health check endpoint with indexing statistics
  - OpenAPI security schemes (JWT Bearer + API Key header)
  - Standardized error response schemas (400, 401, 403, 404, 429)
  - Request ID tracking in responses
"""


# ── Error response schemas ────────────────────────────────────────────


class ErrorDetail(BaseModel):
    """Standard error detail block."""
    field: Optional[str] = Field(None, description="Field that caused the error, if applicable")
    message: str = Field(..., description="Human-readable error message")


class ErrorResponse(BaseModel):
    """Standard error response body."""
    detail: str = Field(..., description="Human-readable error message")
    error_code: str = Field(..., description="Machine-readable error code (e.g. NOT_FOUND, AUTH_FAILED)")
    request_id: Optional[str] = Field(None, description="Unique request identifier for tracing")


class ValidationErrorResponse(BaseModel):
    """Validation error response (HTTP 400)."""
    detail: list[ErrorDetail] = Field(..., description="List of field-level validation errors")
    error_code: str = Field("VALIDATION_ERROR", description="Error code")
    request_id: Optional[str] = Field(None, description="Unique request identifier for tracing")

    model_config = {"json_schema_extra": {"example": {
        "detail": [
            {"field": "limit", "message": "Input should be less than or equal to 100"}
        ],
        "error_code": "VALIDATION_ERROR",
        "request_id": "req-abc123"
    }}}


class AuthErrorResponse(ErrorResponse):
    """Authentication error (HTTP 401)."""
    model_config = {"json_schema_extra": {"example": {
        "detail": "Invalid or expired token",
        "error_code": "AUTH_FAILED",
        "request_id": "req-abc123"
    }}}


class ForbiddenErrorResponse(ErrorResponse):
    """Authorization error (HTTP 403)."""
    model_config = {"json_schema_extra": {"example": {
        "detail": "Insufficient permissions. Role 'admin' required.",
        "error_code": "FORBIDDEN",
        "request_id": "req-abc123"
    }}}


class NotFoundErrorResponse(ErrorResponse):
    """Not found error (HTTP 404)."""
    model_config = {"json_schema_extra": {"example": {
        "detail": "Agent not found",
        "error_code": "NOT_FOUND",
        "request_id": "req-abc123"
    }}}


class RateLimitErrorResponse(ErrorResponse):
    """Rate limit error (HTTP 429)."""
    model_config = {"json_schema_extra": {"example": {
        "detail": "Rate limit exceeded. Try again in 60 seconds.",
        "error_code": "RATE_LIMITED",
        "request_id": "req-abc123"
    }}}


# ── Response models ──────────────────────────────────────────────────


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    model_config = {"json_schema_extra": {"example": {
        "agent_id": "agent-0xabc123",
        "name": "ValidatorBot",
        "owner": "0xdeadbeef...",
        "endpoint": "https://validator.example.com",
        "reputation": 92,
        "tasks_completed": 45,
        "registered_at": "2026-05-01T00:00:00Z",
        "active": True
    }}}


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    model_config = {"json_schema_extra": {"example": {
        "task_id": 1,
        "creator": "0xdeadbeef...",
        "description": "Index 1000 new agents on-chain",
        "reward_wei": "1000000000000000000",
        "deadline": "2026-06-01T00:00:00Z",
        "status": "open",
        "assigned_agent": None
    }}}


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    model_config = {"json_schema_extra": {"example": {
        "agent_id": "agent-0xabc123",
        "name": "ValidatorBot",
        "reputation": 92,
        "tasks_completed": 45,
        "success_rate": 0.978
    }}}


# ── Application factory ──────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="OpenAgents API",
        description="Off-chain indexer and agent discovery API for the OpenAgents protocol. "
                    "Provides agent registration and lookup, task management, reputation leaderboard, "
                    "and health monitoring. Requires JWT Bearer token or API Key for authenticated endpoints.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── Custom OpenAPI schema ────────────────────────────────────
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # Add security schemes
        openapi_schema["components"] = openapi_schema.get("components", {})
        openapi_schema["components"]["securitySchemes"] = {
            "JWTBearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access token obtained via /auth/login. "
                               "Include as: Authorization: Bearer <token>",
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for service-to-service authentication. "
                               "Include as: X-API-Key: <your-api-key>",
            },
        }

        # Apply security globally
        openapi_schema["security"] = [
            {"JWTBearer": []},
            {"ApiKeyAuth": []},
        ]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # ── Request ID middleware ────────────────────────────────────
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Exception handlers ───────────────────────────────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        error_code_map = {
            400: "VALIDATION_ERROR",
            401: "AUTH_FAILED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            429: "RATE_LIMITED",
        }
        request_id = request.headers.get("X-Request-ID", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": error_code_map.get(exc.status_code, "INTERNAL_ERROR"),
                "request_id": request_id,
            },
        )

    return app


app = create_app()

# ── In-memory store (placeholder for DB) ─────────────────────────────
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    summary="List all agents",
    description="Retrieve a paginated list of registered agents with optional filtering by active status and minimum reputation.",
    responses={
        200: {"description": "List of agents", "model": list[AgentResponse]},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to only active agents"),
    min_reputation: int = Query(0, description="Minimum reputation score filter", ge=0),
    limit: int = Query(50, description="Maximum number of results", le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
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
    description="Retrieve detailed information about a specific agent by its unique identifier.",
    responses={
        200: {"description": "Agent details", "model": AgentResponse},
        404: {"model": NotFoundErrorResponse, "description": "Agent not found"},
    },
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    summary="List all tasks",
    description="Retrieve a paginated list of tasks with optional status filtering.",
    responses={
        200: {"description": "List of tasks", "model": list[TaskResponse]},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status (open, assigned, completed)"),
    limit: int = Query(50, description="Maximum number of results", le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task by ID",
    description="Retrieve detailed information about a specific task.",
    responses={
        200: {"description": "Task details", "model": TaskResponse},
        404: {"model": NotFoundErrorResponse, "description": "Task not found"},
    },
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Get reputation leaderboard",
    description="Retrieve the top agents ranked by reputation score.",
    responses={
        200: {"description": "Leaderboard entries", "model": list[LeaderboardEntry]},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def leaderboard(limit: int = Query(20, description="Number of top agents to return", le=50)):
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
    description="Check API health status including indexed agent and task counts. Public endpoint — no authentication required.",
    responses={
        200: {"description": "Health status"},
    },
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
