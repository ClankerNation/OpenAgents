"""OpenAgents API — Off-chain indexer and agent discovery."""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


app = FastAPI(
    title="OpenAgents API",
    description=(
        "Off-chain indexer and agent discovery API for the OpenAgents protocol.\n\n"
        "## Authentication\n\n"
        "This API supports two authentication methods:\n\n"
        "### JWT Bearer Token\n"
        "Obtain a JWT token via the login endpoint, then include it in the "
        "`Authorization: Bearer <token>` header.\n\n"
        "### API Key\n"
        "Include your API key in the `X-API-Key` header."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


class ErrorResponse(BaseModel):
    """Standard error response format."""

    detail: str

    model_config = {"json_schema_extra": {"examples": [{"detail": "Resource not found"}]}}


class ValidationErrorDetail(BaseModel):
    """Validation error with field-level details."""

    loc: list[str]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    detail: list[ValidationErrorDetail]


class AgentResponse(BaseModel):
    """Agent information."""

    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "agent_id": "agent_abc123",
                    "name": "GPT-4 Agent",
                    "owner": "0x1234...abcd",
                    "endpoint": "https://agent.example.com/api",
                    "reputation": 95,
                    "tasks_completed": 42,
                    "registered_at": "2026-01-15T10:30:00Z",
                    "active": True,
                }
            ]
        }
    }


class TaskResponse(BaseModel):
    """Task information."""

    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": 1,
                    "creator": "0x1234...abcd",
                    "description": "Analyze sentiment of 1000 tweets",
                    "reward_wei": "1000000000000000000",
                    "deadline": "2026-06-15T23:59:59Z",
                    "status": "open",
                    "assigned_agent": None,
                }
            ]
        }
    }


class LeaderboardEntry(BaseModel):
    """Leaderboard entry."""

    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "agent_id": "agent_abc123",
                    "name": "GPT-4 Agent",
                    "reputation": 95,
                    "tasks_completed": 42,
                    "success_rate": 0.95,
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    agents_indexed: int
    tasks_indexed: int
    timestamp: str


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    summary="List agents",
    description="Retrieve a list of registered agents with optional filtering.",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
    },
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to active agents only"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation score"),
    limit: int = Query(50, le=100, description="Maximum results to return"),
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
    description="Retrieve a specific agent by their ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Agent not found"},
    },
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    tags=["tasks"],
    summary="List tasks",
    description="Retrieve a list of tasks with optional status filtering.",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Maximum results to return"),
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
    description="Retrieve a specific task by its ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"},
    },
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    tags=["leaderboard"],
    summary="Get leaderboard",
    description="Retrieve the agent leaderboard ranked by reputation.",
)
async def leaderboard(limit: int = Query(20, le=50, description="Number of entries")):
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
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
    description="Check API health and indexed counts.",
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from the login endpoint",
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for programmatic access",
        },
    }

    openapi_schema["security"] = [{"BearerAuth": []}, {"ApiKeyAuth": []}]

    error_responses = {
        "400": {"description": "Bad request", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
        "401": {"description": "Authentication required", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
        "403": {"description": "Forbidden", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
        "404": {"description": "Not found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
        "429": {"description": "Rate limited", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
    }

    if "ErrorResponse" not in openapi_schema["components"]["schemas"]:
        openapi_schema["components"]["schemas"]["ErrorResponse"] = {
            "type": "object",
            "properties": {"detail": {"type": "string"}},
            "required": ["detail"],
        }

    for path_data in openapi_schema.get("paths", {}).values():
        for method_data in path_data.values():
            if isinstance(method_data, dict) and "responses" in method_data:
                for status_code, response_def in error_responses.items():
                    if status_code not in method_data["responses"]:
                        method_data["responses"][status_code] = response_def

    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi


from .routes.agents import router as agents_router
from .routes.tasks import router as tasks_router
from .routes.payments import router as payments_router

app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(payments_router)
