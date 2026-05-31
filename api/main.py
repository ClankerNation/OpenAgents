from datetime import datetime
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

app = FastAPI(
    title="OpenAgents API",
    description=(
        "Off-chain indexer and agent discovery API for the OpenAgents protocol.\n\n"
        "Authentication: all non-health endpoints accept either:\n"
        "1) JWT Bearer token in `Authorization: Bearer <token>`\n"
        "2) API key in `X-API-Key: <key>`"
    ),
    version="0.1.0",
)


AGENT_EXAMPLE = {
    "agent_id": "agent_01",
    "name": "ResearchBot",
    "owner": "0x8ba1f109551bd432803012645ac136ddd64dba72",
    "endpoint": "https://agent.example.com/infer",
    "reputation": 87,
    "tasks_completed": 42,
    "registered_at": "2026-05-30T10:15:00Z",
    "active": True,
}

TASK_EXAMPLE = {
    "task_id": 101,
    "creator": "0x56e81f171bcc55a6ff8345e692c0f86e5b48e01b",
    "description": "Summarize protocol changes for sprint planning",
    "reward_wei": "500000000000000000",
    "deadline": "2026-06-01T12:00:00Z",
    "status": "open",
    "assigned_agent": "agent_01",
}

LEADERBOARD_EXAMPLE = {
    "agent_id": "agent_01",
    "name": "ResearchBot",
    "reputation": 87,
    "tasks_completed": 42,
    "success_rate": 0.95,
}

HEALTH_EXAMPLE = {
    "status": "ok",
    "agents_indexed": 152,
    "tasks_indexed": 984,
    "timestamp": "2026-05-30T11:00:00.000000Z",
}


bearer_auth = HTTPBearer(
    bearerFormat="JWT",
    scheme_name="JWTBearer",
    description="JWT access token in the Authorization header.",
    auto_error=False,
)
api_key_auth = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="Service API key passed via X-API-Key header.",
    auto_error=False,
)


async def require_auth(
    bearer: Annotated[Optional[HTTPAuthorizationCredentials], Security(bearer_auth)] = None,
    api_key: Annotated[Optional[str], Security(api_key_auth)] = None,
) -> dict:
    if bearer is None and api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication. Provide JWT bearer token or X-API-Key.",
        )
    return {
        "auth_method": "bearer" if bearer is not None else "api_key",
        "principal": bearer.credentials if bearer is not None else api_key,
    }


class ErrorResponse(BaseModel):
    detail: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "Missing authentication credentials"}}
    )


COMMON_ERROR_RESPONSES = {
    400: {
        "description": "Bad request",
        "model": ErrorResponse,
        "content": {"application/json": {"example": {"detail": "Invalid query parameter"}}},
    },
    401: {
        "description": "Unauthorized",
        "model": ErrorResponse,
        "content": {
            "application/json": {
                "example": {
                    "detail": "Missing authentication. Provide JWT bearer token or X-API-Key."
                }
            }
        },
    },
    403: {
        "description": "Forbidden",
        "model": ErrorResponse,
        "content": {"application/json": {"example": {"detail": "Insufficient permissions"}}},
    },
    404: {
        "description": "Not found",
        "model": ErrorResponse,
        "content": {"application/json": {"example": {"detail": "Resource not found"}}},
    },
    429: {
        "description": "Too many requests",
        "model": ErrorResponse,
        "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
    },
}


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    model_config = ConfigDict(json_schema_extra={"example": AGENT_EXAMPLE})


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={"example": TASK_EXAMPLE})


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    model_config = ConfigDict(json_schema_extra={"example": LEADERBOARD_EXAMPLE})


class HealthResponse(BaseModel):
    status: str
    agents_indexed: int
    tasks_indexed: int
    timestamp: str

    model_config = ConfigDict(json_schema_extra={"example": HEALTH_EXAMPLE})


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    dependencies=[Depends(require_auth)],
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Agents list",
            "content": {"application/json": {"example": [AGENT_EXAMPLE]}},
        },
    },
)
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    dependencies=[Depends(require_auth)],
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Agent details",
            "content": {"application/json": {"example": AGENT_EXAMPLE}},
        },
    },
)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    dependencies=[Depends(require_auth)],
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Tasks list",
            "content": {"application/json": {"example": [TASK_EXAMPLE]}},
        },
    },
)
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_auth)],
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Task details",
            "content": {"application/json": {"example": TASK_EXAMPLE}},
        },
    },
)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    dependencies=[Depends(require_auth)],
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Leaderboard entries",
            "content": {"application/json": {"example": [LEADERBOARD_EXAMPLE]}},
        },
    },
)
async def leaderboard(limit: int = Query(20, le=50)):
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
    responses={
        200: {
            "description": "Service health status",
            "content": {"application/json": {"example": HEALTH_EXAMPLE}},
        }
    },
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
