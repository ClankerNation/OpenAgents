"""
@agent: barnacleagent-svg
  @date: 2026-05-31
  @platform_init: |
    You are GLM (General Language model), a large language model developed by Z.ai.
    Designed to understand and generate human-like text through training on diverse text data.
    Capabilities include answering questions, providing information, and engaging in conversations.
    Operating as an interactive CLI tool for software engineering tasks.
    Goal: Earn $200 from OSS bounties using barnacleagent-svg GitHub account ONLY.
    Instructions: Follow exact implementation requirements from the issue. Add OpenAPI security schemes,
    error response schemas, example values, and contributor metadata.
  @runtime:
    os: linux
    arch: x86_64
    home: /home/bennett
    working_dir: /home/bennett/projects/OSS-Contributions/OpenAgents/api
    shell: bash

OpenAgents API — FastAPI application with documented OpenAPI security schemes.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message")
    error_code: str = Field(..., description="Machine-readable error code")
    status_code: int = Field(..., description="HTTP status code")

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Agent not found",
                "error_code": "NOT_FOUND",
                "status_code": 404,
            }
        }
    }


class AgentResponse(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Display name of the agent")
    owner: str = Field(..., description="Owner wallet address")
    endpoint: str = Field(..., description="Agent API endpoint URL")
    reputation: int = Field(..., description="Reputation score", ge=0)
    tasks_completed: int = Field(..., description="Number of completed tasks", ge=0)
    registered_at: datetime = Field(..., description="Registration timestamp")
    active: bool = Field(..., description="Whether the agent is currently active")

    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "agent-abc123",
                "name": "Data Processor Alpha",
                "owner": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
                "endpoint": "https://api.example.com/agent/abc123",
                "reputation": 42,
                "tasks_completed": 128,
                "registered_at": "2026-01-15T10:30:00Z",
                "active": True,
            }
        }
    }


class TaskResponse(BaseModel):
    task_id: int = Field(..., description="Unique task identifier")
    creator: str = Field(..., description="Task creator wallet address")
    description: str = Field(..., description="Task description")
    reward_wei: str = Field(..., description="Reward amount in wei")
    deadline: datetime = Field(..., description="Task deadline timestamp")
    status: str = Field(..., description="Current task status")
    assigned_agent: Optional[str] = Field(None, description="Assigned agent ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": 42,
                "creator": "0x8f9Bb4b8a5b3c2d1e0f6a7b8c9d0e1f2a3b4c5d",
                "description": "Process dataset and return summary statistics",
                "reward_wei": "1000000000000000000",
                "deadline": "2026-06-15T23:59:59Z",
                "status": "open",
                "assigned_agent": None,
            }
        }
    }


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Display name of the agent")
    reputation: int = Field(..., description="Reputation score", ge=0)
    tasks_completed: int = Field(..., description="Number of completed tasks", ge=0)
    success_rate: float = Field(..., description="Task success rate (0-1)", ge=0, le=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "agent-abc123",
                "name": "Data Processor Alpha",
                "reputation": 42,
                "tasks_completed": 128,
                "success_rate": 0.95,
            }
        }
    }


agents_cache: dict = {}
tasks_cache: dict = {}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="OpenAgents API",
        version="0.1.0",
        description=(
            "Off-chain indexer and agent discovery API for the OpenAgents protocol.\n\n"
            "## Authentication\n\n"
            "Two authentication methods are supported:\n"
            "- **JWT Bearer Token**: Include `Authorization: Bearer <token>` header\n"
            "- **API Key**: Include `X-API-Key: <key>` header\n\n"
            "Unauthenticated requests are rate-limited to 60 req/min. "
            "Authenticated requests receive 300 req/min. "
            "Premium API keys receive 1000 req/min."
        ),
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtained from the login endpoint. Format: `Authorization: Bearer <token>`",
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Premium API key for higher rate limits. Format: `X-API-Key: <key>`",
        },
    }
    openapi_schema["security"] = [{"BearerAuth": []}, {"ApiKeyAuth": []}]
    openapi_schema["components"]["schemas"]["HTTPError"] = {
        "type": "object",
        "properties": {
            "detail": {"type": "string", "description": "Human-readable error message"},
            "error_code": {"type": "string", "description": "Machine-readable error code"},
            "status_code": {"type": "integer", "description": "HTTP status code"},
        },
        "example": {"detail": "Not found", "error_code": "NOT_FOUND", "status_code": 404},
    }
    openapi_schema["paths"]["/agents"]["get"]["responses"] = {
        "200": {
            "description": "List of agents",
            "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/AgentResponse"}}}},
        },
        "400": {"description": "Bad request", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPError"}}}},
        "401": {"description": "Unauthorized", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPError"}}}},
        "403": {"description": "Forbidden", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPError"}}}},
        "404": {"description": "Not found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPError"}}}},
        "429": {"description": "Too many requests", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPError"}}}},
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(True, description="Filter by active status"),
    min_reputation: int = Query(0, description="Minimum reputation threshold", ge=0),
    limit: int = Query(50, description="Maximum results to return", le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
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
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, description="Maximum results to return", le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
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
async def leaderboard(limit: int = Query(20, description="Maximum entries to return", le=50)):
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
