"""
@contributor-info rafaio1
@timestamp 2026-08-20T11:55:00Z
@env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPBearer, APIKeyHeader
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# --- Security Schemes ---
security_bearer = HTTPBearer(auto_error=False, description="JWT Bearer token for authenticated endpoints")
security_api_key = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key for service-to-service auth")

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    openapi_tags=[
        {"name": "agents", "description": "Agent registration and discovery"},
        {"name": "tasks", "description": "Task management and assignment"},
        {"name": "reputation", "description": "Reputation tracking and leaderboard"},
        {"name": "system", "description": "Health checks and system status"},
    ],
)

# Register security schemes in OpenAPI spec
app.openapi_schema = None  # Force regeneration with security schemes


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
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access token obtained from /auth/login"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Service-to-service API key"
        }
    }
    # Add common error responses
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "required": ["code", "message"],
        "properties": {
            "code": {"type": "string", "example": "VALIDATION_ERROR"},
            "message": {"type": "string", "example": "Request validation failed"},
            "details": {"type": "object", "nullable": True},
            "request_id": {"type": "string", "format": "uuid", "nullable": True}
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="0xabc123...")
    name: str = Field(..., example="ResearchBot-v2")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    endpoint: str = Field(..., example="https://agent.example.com/api")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=42)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=12345)
    creator: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    description: str = Field(..., example="Analyze market data for Q3 report")
    reward_wei: str = Field(..., example="1000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="assigned")
    assigned_agent: Optional[str] = Field(None, example="0xabc123...")


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
