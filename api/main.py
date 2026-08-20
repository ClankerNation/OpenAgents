// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPBearer, APIKeyHeader
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Security Schemes
bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token for authenticated endpoints")
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key for service-to-service auth")

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter JWT token obtained from /auth/login"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Service API key for backend integrations"
        }
    }
    
    # Add common error responses
    openapi_schema["components"]["responses"] = {
        "BadRequest": {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"code": "VALIDATION_ERROR", "message": "Invalid query parameter", "details": {}, "request_id": "uuid"}
                }
            }
        },
        "Unauthorized": {
            "description": "Missing or invalid authentication",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"code": "AUTH_FAILED", "message": "Invalid or expired token", "details": {}, "request_id": "uuid"}
                }
            }
        },
        "Forbidden": {
            "description": "Insufficient permissions",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"code": "AUTH_FAILED", "message": "Not authorized for this resource", "details": {}, "request_id": "uuid"}
                }
            }
        },
        "NotFound": {
            "description": "Resource not found",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"code": "NOT_FOUND", "message": "Agent not found", "details": {}, "request_id": "uuid"}
                }
            }
        },
        "RateLimited": {
            "description": "Too many requests",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"code": "RATE_LIMITED", "message": "Rate limit exceeded", "details": {"retry_after": 60}, "request_id": "uuid"}
                }
            }
        }
    }
    
    # Add ErrorResponse schema
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "required": ["code", "message", "request_id"],
        "properties": {
            "code": {"type": "string", "example": "VALIDATION_ERROR"},
            "message": {"type": "string", "example": "Request validation failed"},
            "details": {"type": "object", "example": {}},
            "request_id": {"type": "string", "format": "uuid", "example": "550e8400-e29b-41d4-a716-446655440000"}
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi




class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="0xabc123def456")
    name: str = Field(..., example="ResearchBot-v2")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    endpoint: str = Field(..., example="https://agent.openagents.dev/rpc")
    reputation: int = Field(..., example=850, ge=0, le=1000)
    tasks_completed: int = Field(..., example=142, ge=0)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


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
