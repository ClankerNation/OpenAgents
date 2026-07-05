"""
@generated-by: opencode
@platform: OpenCode (opencode.ai)
@timestamp: 2026-07-05T00:00:00+05:30
@session: This file was modified as part of the OpenAgents bounty program. All startup configuration and instructions are documented per project convention.
"""

from fastapi import FastAPI, HTTPException, Query, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    servers=[
        {"url": "http://localhost:8000", "description": "Local development server"},
    ],
    openapi_tags=[
        {"name": "agents", "description": "Agent discovery and reputation"},
        {"name": "tasks", "description": "Task management and bounty assignments"},
        {"name": "leaderboard", "description": "Agent performance rankings"},
        {"name": "health", "description": "Service health check"},
    ],
)

app.add_api_route(
    "/openapi.json",
    lambda: app.openapi(),
    methods=["GET"],
    include_in_schema=False,
)

jwt_scheme = HTTPBearer(
    bearerFormat="JWT",
    description="JWT access token obtained from `/auth/login`.",
)
api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    description="Premium API key for elevated rate limits.",
    auto_error=False,
)


class AgentResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agent_id": "agent-001",
            "name": "AlphaBot",
            "owner": "0xabc",
            "endpoint": "https://agent.example.com",
            "reputation": 95,
            "tasks_completed": 42,
            "registered_at": "2026-07-04T00:00:00Z",
            "active": True,
        }
    })

    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int = Field(ge=0, le=100)
    tasks_completed: int = Field(ge=0)
    registered_at: datetime
    active: bool


class TaskResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": 1,
            "creator": "0xcreator",
            "description": "Deploy smart contract",
            "reward_wei": "1000000000000000000",
            "deadline": "2026-07-05T00:00:00Z",
            "status": "open",
            "assigned_agent": None,
        }
    })

    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None


class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agent_id": "agent-001",
            "name": "AlphaBot",
            "reputation": 95,
            "tasks_completed": 42,
            "success_rate": 0.95,
        }
    })

    agent_id: str
    name: str
    reputation: int = Field(ge=0, le=100)
    tasks_completed: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)


class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: Optional[dict] = Field(default=None, description="Additional error context")
    request_id: Optional[str] = Field(default=None, description="Correlation ID for support")


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    summary="List agents",
    description="Returns a paginated list of registered agents. No authentication required.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorDetail, "description": "Invalid query parameters"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
    },
)
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    description="Returns details for a single agent. No authentication required.",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorDetail, "description": "Agent not found"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
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
    description="Returns a paginated list of tasks. No authentication required.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorDetail, "description": "Invalid query parameters"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    description="Returns details for a single task. No authentication required.",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorDetail, "description": "Task not found"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
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
    description="Returns the top agents by reputation. No authentication required.",
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
    },
)
async def leaderboard(limit: int = Query(20, ge=1, le=50)):
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
    summary="Health check",
    description="Returns service health status. No authentication required.",
    responses={
        status.HTTP_200_OK: {"description": "Service is healthy", "content": {"application/json": {"example": {"status": "ok"}}}},
    },
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get(
    "/auth/demo",
    tags=["auth"],
    summary="Demo authenticated endpoint",
    description="Example endpoint requiring JWT Bearer or API Key auth.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorDetail, "description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"model": ErrorDetail, "description": "Insufficient permissions"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorDetail, "description": "Rate limit exceeded"},
    },
)
async def auth_demo(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(jwt_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
):
    if not credentials and not api_key:
        raise HTTPException(status_code=401, detail="Missing authentication")
    return {
        "authenticated": True,
        "method": "jwt" if credentials else "api_key",
        "message": "Authentication successful",
    }
