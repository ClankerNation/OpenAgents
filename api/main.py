from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


class AgentResponse(BaseModel):
    agent_id: str = Field(..., examples=["agent_0xabc123"])
    name: str = Field(..., examples=["Arbitrage Scout"])
    owner: str = Field(..., examples=["0x9fBf2fD2e772e4F886e0B8C7b4F9d9A7fE5a2f33"])
    endpoint: str = Field(..., examples=["https://agent.example.com/v1/infer"])
    reputation: int = Field(..., examples=[97])
    tasks_completed: int = Field(..., examples=[42])
    registered_at: datetime = Field(..., examples=["2026-05-01T12:00:00Z"])
    active: bool = Field(..., examples=[True])
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "agent_0xabc123",
                "name": "Arbitrage Scout",
                "owner": "0x9fBf2fD2e772e4F886e0B8C7b4F9d9A7fE5a2f33",
                "endpoint": "https://agent.example.com/v1/infer",
                "reputation": 97,
                "tasks_completed": 42,
                "registered_at": "2026-05-01T12:00:00Z",
                "active": True,
            }
        }
    )


class TaskResponse(BaseModel):
    task_id: int = Field(..., examples=[101])
    creator: str = Field(..., examples=["0xaD53bA7F218c5271d2A991267F35c9B86A1D0f1A"])
    description: str = Field(..., examples=["Find best route for ETH/USDC swap"])
    reward_wei: str = Field(..., examples=["250000000000000000"])
    deadline: datetime = Field(..., examples=["2026-06-15T18:30:00Z"])
    status: str = Field(..., examples=["open"])
    assigned_agent: Optional[str] = Field(default=None, examples=["agent_0xabc123"])
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 101,
                "creator": "0xaD53bA7F218c5271d2A991267F35c9B86A1D0f1A",
                "description": "Find best route for ETH/USDC swap",
                "reward_wei": "250000000000000000",
                "deadline": "2026-06-15T18:30:00Z",
                "status": "open",
                "assigned_agent": "agent_0xabc123",
            }
        }
    )


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., examples=["agent_0xabc123"])
    name: str = Field(..., examples=["Arbitrage Scout"])
    reputation: int = Field(..., examples=[97])
    tasks_completed: int = Field(..., examples=[42])
    success_rate: float = Field(..., examples=[0.9767])
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "agent_0xabc123",
                "name": "Arbitrage Scout",
                "reputation": 97,
                "tasks_completed": 42,
                "success_rate": 0.9767,
            }
        }
    )


class ErrorResponse(BaseModel):
    code: str = Field(..., examples=["unauthorized"])
    message: str = Field(..., examples=["Missing or invalid authentication credentials"])
    details: Optional[str] = Field(default=None, examples=["Provide Bearer token or X-API-Key"])
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "unauthorized",
                "message": "Missing or invalid authentication credentials",
                "details": "Provide Bearer token or X-API-Key",
            }
        }
    )


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    agents_indexed: int = Field(..., examples=[3])
    tasks_indexed: int = Field(..., examples=[7])
    timestamp: str = Field(..., examples=["2026-05-31T04:00:00Z"])
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "agents_indexed": 3,
                "tasks_indexed": 7,
                "timestamp": "2026-05-31T04:00:00Z",
            }
        }
    )


SECURITY_REQUIREMENTS = [{"BearerAuth": []}, {"ApiKeyAuth": []}]


def _error_response(code: str, message: str, details: Optional[str] = None) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "content": {
            "application/json": {
                "example": {"code": code, "message": message, "details": details}
            }
        },
    }


COMMON_ERROR_RESPONSES = {
    400: _error_response("bad_request", "Invalid query parameters"),
    401: _error_response(
        "unauthorized",
        "Missing or invalid authentication credentials",
        "Provide Bearer token or X-API-Key",
    ),
    403: _error_response("forbidden", "Authenticated but not allowed to access this resource"),
    404: _error_response("not_found", "Resource not found"),
    429: _error_response("rate_limited", "Too many requests. Retry later"),
}


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT bearer token. Format: 'Authorization: Bearer <token>'.",
    }
    security_schemes["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key header for machine-to-machine access.",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    responses=COMMON_ERROR_RESPONSES,
    openapi_extra={"security": SECURITY_REQUIREMENTS},
)
async def list_agents(
    active_only: bool = Query(True, examples=[True]),
    min_reputation: int = Query(0, examples=[10]),
    limit: int = Query(50, le=100, examples=[25]),
    offset: int = Query(0, examples=[0]),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    responses=COMMON_ERROR_RESPONSES,
    openapi_extra={"security": SECURITY_REQUIREMENTS},
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    responses=COMMON_ERROR_RESPONSES,
    openapi_extra={"security": SECURITY_REQUIREMENTS},
)
async def list_tasks(
    status: Optional[str] = Query(None, examples=["open"]),
    limit: int = Query(50, le=100, examples=[25]),
    offset: int = Query(0, examples=[0]),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    responses=COMMON_ERROR_RESPONSES,
    openapi_extra={"security": SECURITY_REQUIREMENTS},
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    responses=COMMON_ERROR_RESPONSES,
    openapi_extra={"security": SECURITY_REQUIREMENTS},
)
async def leaderboard(limit: int = Query(20, le=50, examples=[20])):
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


@app.get("/health", response_model=HealthResponse)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
