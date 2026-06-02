# Contributor: Feltchy
# Platform: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
# Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash, /home/owner/.openclaw/workspace
from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.models import SecurityScheme as SecuritySchemeModel
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, APIKeyHeader
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Security schemes for OpenAPI documentation
bearer_scheme = HTTPBearer(
    scheme_name="JWT",
    description="Bearer token from /auth/login. Format: Bearer eyJ...",
    auto_error=False,
)
api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    scheme_name="API Key",
    description="API key from /auth/api-keys. Format: ok_...",
    auto_error=False,
)

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    openapi_tags=[
        {"name": "agents", "description": "Agent discovery and metadata"},
        {"name": "tasks", "description": "Task listing and status"},
        {"name": "leaderboard", "description": "Agent reputation rankings"},
        {"name": "health", "description": "Service health check"},
    ],
)

# Custom OpenAPI schema with security and error responses
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "JWT": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Bearer token from /auth/login",
        },
        "API Key": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key from /auth/api-keys",
        },
    }
    openapi_schema["security"] = [{"JWT": []}, {"API Key": []}]
    
    # Add error response schemas
    openapi_schema["components"]["schemas"] = openapi_schema["components"].get("schemas", {})
    openapi_schema["components"]["schemas"]["HTTPError"] = {
        "type": "object",
        "properties": {"detail": {"type": "string"}},
        "example": {"detail": "Error description"},
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


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


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    tags=["agents"],
    responses={401: {"description": "Invalid or missing auth", "model": BaseModel}},
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
    tags=["agents"],
    responses={
        401: {"description": "Invalid or missing auth"},
        404: {"description": "Agent not found"},
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
    responses={401: {"description": "Invalid or missing auth"}},
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
    tags=["tasks"],
    responses={
        401: {"description": "Invalid or missing auth"},
        404: {"description": "Task not found"},
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
    responses={401: {"description": "Invalid or missing auth"}},
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
    tags=["health"],
    responses={200: {"description": "Service is healthy"}},
)
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
