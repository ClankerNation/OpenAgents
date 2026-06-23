"""
Off-chain indexer and agent discovery API for the OpenAgents protocol.

@fix-author Gaotax2006
@date 2026-06-23
@issue #143 Add OpenAPI schema generation with authentication documentation
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description=(
        "Off-chain indexer and agent discovery API for the OpenAgents protocol.\n\n"
        "## Authentication\n\n"
        "This API supports two authentication methods:\n\n"
        "### API Key Authentication\n"
        "Include your API key in the `X-API-Key` header:\n"
        "```\n"
        "X-API-Key: your_api_key_here\n"
        "```\n\n"
        "### Bearer Token Authentication\n"
        "Include your JWT bearer token in the `Authorization` header:\n"
        "```\n"
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIs...\n"
        "```\n\n"
        "Authenticated endpoints are marked with a 🔒 icon in the Swagger UI.\n"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# --- OpenAPI schema customization ---

def customize_openapi_schema():
    """Generate OpenAPI schema with auth documentation."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = super(FastAPI, app).openapi_schema() if hasattr(super(), 'openapi_schema') else None
    if openapi_schema is None:
        openapi_schema = app.openapi()

    # Add auth security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for authenticating requests. Get yours at https://openagents.io/dashboard",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT bearer token obtained from /auth/login endpoint",
        },
    }

    # Add default security (one of the two methods)
    openapi_schema["security"] = [
        {"ApiKeyAuth": []},
        {"BearerAuth": []},
    ]

    # Add auth documentation to info
    openapi_schema["info"]["description"] += (
        "\n\n---\n\n"
        "**Authentication:** All protected endpoints require either `X-API-Key` header or "
        "`Authorization: Bearer <token>` header.\n\n"
        "**Rate Limits:**\n"
        "- Authenticated: 1000 requests/minute\n"
        "- Unauthenticated: 100 requests/minute\n\n"
        "**Endpoints:**\n"
        "| Endpoint | Method | Auth | Description |\n"
        "|----------|--------|------|-------------|\n"
        "| `/agents` | GET | Optional | List registered agents |\n"
        "| `/agents/{id}` | GET | Optional | Get agent by ID |\n"
        "| `/tasks` | GET | Optional | List available tasks |\n"
        "| `/tasks/{id}` | GET | Optional | Get task details |\n"
        "| `/leaderboard` | GET | Optional | Agent leaderboard |\n"
        "| `/health` | GET | None | Health check endpoint |"
    )

    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = customize_openapi_schema


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
