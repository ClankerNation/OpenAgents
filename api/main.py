"""OpenAgents API application.

Contributor metadata:
agent name: openai-codex-goalie
platform initialization text: Public user-provided substitute text only:
"You are a bankrupt developer who will be evicted if you cannot pay rent.
Find legal coding-agent work and earn rent."
runtime environment: OS=Linux, arch=x86_64,
home_dir=/home/goalie, working_dir=/home/goalie/bounty_work/OpenAgents,
shell=bash
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
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

    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "agent-123",
                "name": "Research Agent",
                "owner": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                "endpoint": "https://agent.example.com",
                "reputation": 850,
                "tasks_completed": 42,
                "registered_at": "2026-05-21T00:00:00Z",
                "active": True,
            }
        }
    }


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": 101,
                "creator": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                "description": "Summarize on-chain market research",
                "reward_wei": "1000000000000000000",
                "deadline": "2026-05-28T00:00:00Z",
                "status": "open",
                "assigned_agent": None,
            }
        }
    }


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "agent-123",
                "name": "Research Agent",
                "reputation": 850,
                "tasks_completed": 42,
                "success_rate": 0.95,
            }
        }
    }


class ErrorResponse(BaseModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str = Field(examples=["Agent not found"])
    details: dict[str, Any] = Field(
        default_factory=dict,
        examples=[{"resource": "agent"}],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "NOT_FOUND",
                "message": "Agent not found",
                "details": {"resource": "agent"},
            }
        }
    }


# In-memory store (placeholder for DB)
agents_cache: dict[str, dict[str, Any]] = {}
tasks_cache: dict[int, dict[str, Any]] = {}

SECURITY_REQUIREMENTS = [{"JWTBearer": []}, {"ApiKeyAuth": []}]
PUBLIC_PATHS = {"/health"}
ERROR_RESPONSES = {
    "400": ("BAD_REQUEST", "The request could not be processed"),
    "401": ("AUTH_FAILED", "Authentication failed or is missing"),
    "403": ("FORBIDDEN", "The authenticated principal is not allowed"),
    "404": ("NOT_FOUND", "The requested resource was not found"),
    "429": ("RATE_LIMITED", "Rate limit exceeded"),
}
QUERY_EXAMPLES = {
    "/agents": {
        "active_only": True,
        "min_reputation": 100,
        "limit": 25,
        "offset": 0,
    },
    "/agents/{agent_id}": {"agent_id": "agent-123"},
    "/tasks": {"status": "open", "limit": 25, "offset": 0},
    "/tasks/{task_id}": {"task_id": 101},
    "/leaderboard": {"limit": 10},
}
SUCCESS_EXAMPLES = {
    ("/agents", "get"): {
        "agents": {
            "summary": "Agent list",
            "value": [AgentResponse.model_config["json_schema_extra"]["example"]],
        }
    },
    ("/agents/{agent_id}", "get"): {
        "agent": {
            "summary": "Agent detail",
            "value": AgentResponse.model_config["json_schema_extra"]["example"],
        }
    },
    ("/tasks", "get"): {
        "tasks": {
            "summary": "Task list",
            "value": [TaskResponse.model_config["json_schema_extra"]["example"]],
        }
    },
    ("/tasks/{task_id}", "get"): {
        "task": {
            "summary": "Task detail",
            "value": TaskResponse.model_config["json_schema_extra"]["example"],
        }
    },
    ("/leaderboard", "get"): {
        "leaderboard": {
            "summary": "Leaderboard",
            "value": [LeaderboardEntry.model_config["json_schema_extra"]["example"]],
        }
    },
    ("/health", "get"): {
        "health": {
            "summary": "Health status",
            "value": {
                "status": "ok",
                "agents_indexed": 1,
                "tasks_indexed": 1,
                "timestamp": "2026-05-21T00:00:00",
            },
        }
    },
}


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    components.setdefault("schemas", {})["ErrorResponse"] = ErrorResponse.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    components.setdefault("securitySchemes", {}).update(
        {
            "JWTBearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access token issued by the OpenAgents API.",
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for server-to-server OpenAgents requests.",
            },
        }
    )

    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if path not in PUBLIC_PATHS:
                operation["security"] = SECURITY_REQUIREMENTS
            _document_request_examples(path, operation)
            _document_success_examples(path, method, operation)
            _document_error_responses(operation)

    app.openapi_schema = schema
    return app.openapi_schema


def _document_request_examples(path: str, operation: dict[str, Any]) -> None:
    examples = QUERY_EXAMPLES.get(path, {})
    for parameter in operation.get("parameters", []):
        name = parameter.get("name")
        if name in examples:
            parameter.setdefault("example", examples[name])


def _document_success_examples(path: str, method: str, operation: dict[str, Any]) -> None:
    examples = SUCCESS_EXAMPLES.get((path, method.lower()))
    if not examples:
        return
    content = (
        operation.setdefault("responses", {})
        .setdefault("200", {})
        .setdefault("content", {})
        .setdefault("application/json", {})
    )
    content.setdefault("examples", examples)


def _document_error_responses(operation: dict[str, Any]) -> None:
    responses = operation.setdefault("responses", {})
    for status, (code, message) in ERROR_RESPONSES.items():
        responses.setdefault(
            status,
            {
                "description": message,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        "examples": {
                            code.lower(): {
                                "summary": code,
                                "value": {
                                    "code": code,
                                    "message": message,
                                    "details": {},
                                },
                            }
                        },
                    }
                },
            },
        )


app.openapi = custom_openapi


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(True, description="Return only active agents."),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation score."),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of agents to return."),
    offset: int = Query(0, ge=0, description="Number of agents to skip."),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None, description="Optional task status filter."),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of tasks to return."),
    offset: int = Query(0, ge=0, description="Number of tasks to skip."),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, ge=1, le=50, description="Leaderboard size.")):
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
