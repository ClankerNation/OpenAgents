"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. You have persistent memory across sessions. Save durable facts using the memory tool. Skills: ai-comic-pipeline, bounty (clawwork, gitcoin), dreamina-cli, finance (tushare-pro). Host: Windows (10). User home directory: C:\Users\57629. Shell: git-bash / MSYS. You are on Weixin/WeChat. Conversation: 2026-05-28 09:08, deepseek-v4-flash/deepseek.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash

from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .routes import admin as admin_router
from .middleware.errors import (
    RequestIDMiddleware,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
    AppError,
)
from fastapi.exceptions import RequestValidationError

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register error handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)


def custom_openapi():
    """Generate OpenAPI schema with security schemes and error responses."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="OpenAgents API",
        version="0.1.0",
        description="Off-chain indexer and agent discovery API for the OpenAgents protocol\n\n"
        "## Authentication\n"
        "- **JWT Bearer Token**: Required for authenticated endpoints. Obtain via login.\n"
        "- **API Key**: Alternative auth for programmatic access via `X-API-Key` header.\n\n"
        "## Error Responses\n"
        "All errors follow the structured format: `{code, message, details, request_id}`\n"
        "- `VALIDATION_ERROR` (400/422): Input validation failures\n"
        "- `NOT_FOUND` (404): Resource not found\n"
        "- `AUTH_FAILED` (401/403): Authentication/authorization failures\n"
        "- `RATE_LIMITED` (429): Rate limit exceeded\n"
        "- `INTERNAL_ERROR` (500): Unexpected server errors",
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "JWTBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token. Obtain via /auth/login endpoint.",
        },
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Alternative API key authentication.",
        },
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"JWTBearer": []}, {"APIKeyHeader": []}]
    
    # Add error response schema
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Error code", "example": "NOT_FOUND"},
            "message": {"type": "string", "description": "Human-readable error message", "example": "Agent not found"},
            "details": {"type": "object", "description": "Additional error details", "example": {"field": "name"}},
            "request_id": {"type": "string", "description": "Unique request identifier", "example": "abc12345"},
        },
    }
    
    # Add validation error schema
    openapi_schema["components"]["schemas"]["ValidationError"] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "example": "VALIDATION_ERROR"},
            "message": {"type": "string", "example": "Request validation failed"},
            "details": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "example": {"body.name": "field required"},
                    }
                },
            },
            "request_id": {"type": "string", "example": "abc12345"},
        },
    }
    
    # Add example models
    openapi_schema["components"]["schemas"]["AgentResponse"] = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "example": "agent_abc123"},
            "name": {"type": "string", "example": "My Trading Agent"},
            "owner": {"type": "string", "example": "0x1234567890abcdef1234567890abcdef12345678"},
            "endpoint": {"type": "string", "example": "https://api.myagent.com/webhook"},
            "reputation": {"type": "integer", "example": 85},
            "tasks_completed": {"type": "integer", "example": 42},
            "active": {"type": "boolean", "example": True},
        },
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Register admin routes
app.include_router(admin_router.router)


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


@app.get("/agents", response_model=list[AgentResponse])
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


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
