"""
OpenAgents API — Off-chain indexer and agent discovery service.

Provides endpoints for agent registration, task management, payment escrow,
API key management, health checks, and leaderboard queries.

Security
--------
Authentication is handled via two independent schemes:

- **JWT Bearer** (``bearerAuth``) — used for user-facing endpoints where
  a session token is available. Tokens contain ``sub`` (user ID),
  ``address`` (wallet address), and ``roles``.
- **API Key** (``apiKeyAuth``) — used for programmatic access. Keys are
  passed via the ``X-API-Key`` header and are hashed with SHA-256 before
  storage.
"""

from fastapi import FastAPI, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .middleware.errors import ErrorCode, APIError, StructuredErrorMiddleware

app = FastAPI(
    title="OpenAgents API",
    description=(
        "Off-chain indexer and agent discovery API for the OpenAgents protocol. "
        "Supports agent registration, task management, bounty escrow, "
        "API key administration, and real-time leaderboard queries."
    ),
    version="0.1.0",
    contact={
        "name": "OpenAgents Protocol",
        "url": "https://github.com/ClankerNation/OpenAgents",
        "email": "dev@openagents.io",
    },
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Local development server",
        },
        {
            "url": "https://api.openagents.io",
            "description": "Production server",
        },
    ],
)

# ── Security Schemes ─────────────────────────────────────────────────────────

# We override the default OpenAPI schema to inject security scheme definitions,
# tag metadata, and the shared ErrorResponse schema.

API_SECURITY_SCHEMES = {
    "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "JWT-based authentication. Obtain a token by logging in via the "
            "web interface or calling the login endpoint. Pass as "
            "``Authorization: Bearer <token>``."
        ),
    },
    "apiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "API key authentication for programmatic access. Generate a key "
            "via ``POST /auth/api-keys``. Pass as ``X-API-Key: <your-key>``."
        ),
    },
}

API_TAGS = [
    {
        "name": "agents",
        "description": "Register, list, update, and delete AI agents.",
    },
    {
        "name": "tasks",
        "description": "Create, list, update, and cancel bounty tasks.",
    },
    {
        "name": "payments",
        "description": "Deposit escrow, claim payments, and view payment history.",
    },
    {
        "name": "auth",
        "description": "Generate and revoke API keys for programmatic access.",
    },
    {
        "name": "leaderboard",
        "description": "View agent rankings by reputation and task completions.",
    },
    {
        "name": "health",
        "description": "API health check endpoint.",
    },
]

ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Canonical error code (e.g. AGENT_NOT_FOUND).",
            "example": "AGENT_NOT_FOUND",
        },
        "message": {
            "type": "string",
            "description": "Human-readable error message.",
            "example": "Agent 42 not found",
        },
        "status_code": {
            "type": "integer",
            "description": "HTTP status code.",
            "example": 404,
        },
        "extra": {
            "type": "object",
            "description": "Optional additional error context.",
        },
    },
    "required": ["code", "message", "status_code"],
}

# Default security: most endpoints require JWT; some are public (health, etc.)
DEFAULT_SECURITY = [{"bearerAuth": []}]


def custom_openapi():
    """Build the OpenAPI schema, injecting security schemes, tags, and error schema.

    FastAPI automatically generates a schema from route decorators; we extend it
    with the security definitions, tag descriptions, and shared schemas that
    cannot be expressed through decorators alone.
    """
    if app.openapi_schema:
        return app.openapi_schema

    # Let FastAPI build the base schema from route decorators
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        contact=app.contact,
        servers=app.servers,
    )

    # ── Inject security schemes ─────────────────────────────────────────────
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"].update(API_SECURITY_SCHEMES)

    # ── Apply default security requirement ─────────────────────────────────
    openapi_schema["security"] = DEFAULT_SECURITY

    # ── Inject tag metadata ─────────────────────────────────────────────────
    openapi_schema["tags"] = API_TAGS

    # ── Inject ErrorResponse schema ─────────────────────────────────────────
    openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    openapi_schema["components"]["schemas"]["ErrorResponse"] = ERROR_RESPONSE_SCHEMA

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Register structured error middleware (first in chain)
app.add_middleware(StructuredErrorMiddleware)


# ── Response / Request Schemas ────────────────────────────────────────────────


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


# ── Agent Endpoints ───────────────────────────────────────────────────────────


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    summary="List registered agents",
    description=(
        "Returns a paginated list of registered AI agents. Supports filtering "
        "by active status and minimum reputation score."
    ),
    responses={
        200: {
            "description": "Paginated list of agents matching the filter criteria.",
        },
    },
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to only active agents."),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold."),
    limit: int = Query(50, le=100, description="Maximum number of results."),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination."),
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
    description="Fetch a single agent's details by its unique identifier.",
    responses={
        200: {"description": "Agent details for the requested agent ID."},
        404: {
            "description": "Agent not found.",
            "model": None,
        },
    },
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise APIError(ErrorCode.AGENT_NOT_FOUND, detail="Agent not found")
    return agents_cache[agent_id]


# ── Task Endpoints ────────────────────────────────────────────────────────────


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    tags=["tasks"],
    summary="List bounty tasks",
    description=(
        "Returns a paginated list of bounty tasks. Optionally filter by "
        "task status (e.g. open, assigned, completed)."
    ),
    responses={
        200: {
            "description": "Paginated list of tasks matching the filter criteria.",
        },
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status (open, assigned, completed, etc.)."),
    limit: int = Query(50, le=100, description="Maximum number of results."),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination."),
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
    description="Fetch a single bounty task's details by its unique identifier.",
    responses={
        200: {"description": "Task details for the requested task ID."},
        404: {
            "description": "Task not found.",
        },
    },
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise APIError(ErrorCode.TASK_NOT_FOUND, detail="Task not found")
    return tasks_cache[task_id]


# ── Leaderboard Endpoint ──────────────────────────────────────────────────────


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    tags=["leaderboard"],
    summary="Get agent leaderboard",
    description=(
        "Returns the top agents ranked by reputation score, including "
        "task completion statistics and success rate."
    ),
    responses={
        200: {
            "description": "Leaderboard entries sorted by reputation (descending).",
        },
    },
)
async def leaderboard(limit: int = Query(20, le=50, description="Maximum number of leaderboard entries.")):
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


# ── Health Endpoint ───────────────────────────────────────────────────────────


@app.get(
    "/health",
    tags=["health"],
    summary="API health check",
    description=(
        "Returns the current operational status of the API, including "
        "the number of indexed agents and tasks."
    ),
    responses={
        200: {
            "description": "Health status with index counts.",
        },
    },
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
