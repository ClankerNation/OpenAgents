"""
@contributor-info
@identity OpenAI Codex (GPT-5)
@session_initialization_context
# AGENTS.md instructions for F:\\jiedan
- Autonomy directive enabled; execute to completion without permission handoff for safe, reversible steps.
- Workspace contract includes OMX orchestration guidance, verification before completion, and minimal diff preference.
- Active user task: only issue #185 with clean baseline from origin/main, minimal implementation, targeted tests, commit/push/PR.
@environment
- operating_system: Microsoft Windows 11 家庭中文版
- processor_architecture: x64
- home_directory: C:\\Users\\55093
- working_directory: F:\\jiedan\\OpenAgents-185
- shell_binary_path: C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

bearer_auth = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="JWT Bearer token. Format: 'Authorization: Bearer <token>'.",
)
api_key_auth = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="ApiKeyAuth",
    description="API Key header. Format: 'X-API-Key: <api_key>'.",
)

AUTH_SECURITY = [{"BearerAuth": []}, {"ApiKeyAuth": []}]


class ErrorResponse(BaseModel):
    error: str
    message: str
    code: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "unauthorized",
                "message": "Missing JWT bearer token or API key",
                "code": 401,
            }
        }
    )


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "agent_01",
                "name": "Routing Agent",
                "owner": "0x1111111111111111111111111111111111111111",
                "endpoint": "https://agents.example.com/router",
                "reputation": 98,
                "tasks_completed": 412,
                "registered_at": "2026-01-10T08:30:00Z",
                "active": True,
            }
        }
    )


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 1001,
                "creator": "0x2222222222222222222222222222222222222222",
                "description": "Summarize governance proposal changes",
                "reward_wei": "50000000000000000",
                "deadline": "2026-06-01T15:00:00Z",
                "status": "open",
                "assigned_agent": "agent_01",
            }
        }
    )


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "agent_01",
                "name": "Routing Agent",
                "reputation": 98,
                "tasks_completed": 412,
                "success_rate": 0.9976,
            }
        }
    )


class HealthResponse(BaseModel):
    status: str
    agents_indexed: int
    tasks_indexed: int
    timestamp: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "agents_indexed": 1,
                "tasks_indexed": 1,
                "timestamp": "2026-05-30T12:00:00.000000",
            }
        }
    )


COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    400: {
        "model": ErrorResponse,
        "description": "Bad Request",
        "content": {
            "application/json": {
                "example": {
                    "error": "bad_request",
                    "message": "Invalid request parameters",
                    "code": 400,
                }
            }
        },
    },
    401: {
        "model": ErrorResponse,
        "description": "Unauthorized",
        "content": {
            "application/json": {
                "example": {
                    "error": "unauthorized",
                    "message": "Missing JWT bearer token or API key",
                    "code": 401,
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Forbidden",
        "content": {
            "application/json": {
                "example": {
                    "error": "forbidden",
                    "message": "Authenticated, but not allowed for this resource",
                    "code": 403,
                }
            }
        },
    },
    404: {
        "model": ErrorResponse,
        "description": "Not Found",
        "content": {
            "application/json": {
                "example": {
                    "error": "not_found",
                    "message": "Requested resource was not found",
                    "code": 404,
                }
            }
        },
    },
    429: {
        "model": ErrorResponse,
        "description": "Too Many Requests",
        "content": {
            "application/json": {
                "example": {
                    "error": "rate_limited",
                    "message": "Too many requests, please retry later",
                    "code": 429,
                }
            }
        },
    },
}


async def require_auth(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth),
    api_key: Optional[str] = Security(api_key_auth),
) -> None:
    if bearer is None and not api_key:
        raise HTTPException(
            status_code=401, detail="Missing JWT bearer token or API key"
        )


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    dependencies=[Depends(require_auth)],
    openapi_extra={"security": AUTH_SECURITY},
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "List of indexed agents",
            "content": {
                "application/json": {"example": [AgentResponse.model_config["json_schema_extra"]["example"]]}
            },
        },
    },
)
async def list_agents(
    active_only: bool = Query(
        True,
        openapi_examples={
            "active_only": {"summary": "Only active agents", "value": True}
        },
    ),
    min_reputation: int = Query(
        0,
        openapi_examples={
            "trusted_only": {"summary": "Trusted agents only", "value": 80}
        },
    ),
    limit: int = Query(
        50,
        le=100,
        openapi_examples={"first_page": {"summary": "First page size", "value": 25}},
    ),
    offset: int = Query(
        0,
        openapi_examples={
            "next_page": {"summary": "Pagination offset", "value": 25}
        },
    ),
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
    openapi_extra={"security": AUTH_SECURITY},
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Agent details",
            "content": {
                "application/json": {"example": AgentResponse.model_config["json_schema_extra"]["example"]}
            },
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
    openapi_extra={"security": AUTH_SECURITY},
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "List of indexed tasks",
            "content": {
                "application/json": {"example": [TaskResponse.model_config["json_schema_extra"]["example"]]}
            },
        },
    },
)
async def list_tasks(
    status: Optional[str] = Query(
        None,
        openapi_examples={"open_tasks": {"summary": "Open tasks only", "value": "open"}},
    ),
    limit: int = Query(
        50,
        le=100,
        openapi_examples={"first_page": {"summary": "First page size", "value": 25}},
    ),
    offset: int = Query(
        0,
        openapi_examples={
            "next_page": {"summary": "Pagination offset", "value": 25}
        },
    ),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_auth)],
    openapi_extra={"security": AUTH_SECURITY},
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Task details",
            "content": {
                "application/json": {"example": TaskResponse.model_config["json_schema_extra"]["example"]}
            },
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
    openapi_extra={"security": AUTH_SECURITY},
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Leaderboard entries",
            "content": {
                "application/json": {"example": [LeaderboardEntry.model_config["json_schema_extra"]["example"]]}
            },
        },
    },
)
async def leaderboard(
    limit: int = Query(
        20,
        le=50,
        openapi_examples={"top_10": {"summary": "Top 10", "value": 10}},
    )
):
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
            "description": "Health status",
            "content": {
                "application/json": {"example": HealthResponse.model_config["json_schema_extra"]["example"]}
            },
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
