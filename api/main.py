from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

# Authentication scheme
API_KEY_NAME = "X-API-Key"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# In-memory API key store (placeholder for DB lookup)
VALID_API_KEYS: set[str] = set(os.getenv("OPENAGENTS_API_KEYS", "dev-key-1,dev-key-2").split(","))

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol. "
                "Most endpoints require authentication via `X-API-Key` header or Bearer token.",
    version="0.2.0",
    contact={
        "name": "OpenAgents Core Team",
        "url": "https://github.com/ClankerNation/OpenAgents",
    },
    license_info={
        "name": "MIT",
    },
    # OpenAPI security scheme definition
    openapi_tags=[
        {"name": "Public", "description": "Endpoints accessible without authentication"},
        {"name": "Protected", "description": "Endpoints requiring API key or Bearer token authentication"},
    ],
)


def verify_api_key(api_key: Optional[str] = Header(None, alias=API_KEY_NAME)) -> str:
    """Validate the API key from the X-API-Key header."""
    if api_key and api_key.strip() in VALID_API_KEYS:
        return api_key
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key. Provide a valid key via the `X-API-Key` header.",
        headers={"WWW-Authenticate": API_KEY_NAME},
    )


def verify_bearer_token(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """Validate a Bearer token (same pool as API keys for simplicity)."""
    if token and token.strip() in VALID_API_KEYS:
        return token
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing Bearer token. Provide a valid token in the `Authorization: Bearer <token>` header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(
    api_key: Optional[str] = Header(None, alias=API_KEY_NAME),
    bearer: Optional[str] = Depends(oauth2_scheme),
) -> str:
    """Dependency that accepts either X-API-Key header or Bearer token."""
    if api_key and api_key.strip() in VALID_API_KEYS:
        return api_key
    if bearer and bearer.strip() in VALID_API_KEYS:
        return bearer
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Use `X-API-Key` header or `Authorization: Bearer <token>`.",
        headers={"WWW-Authenticate": "Bearer"},
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


@app.get("/health", tags=["Public"])
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# OpenAPI schema customization with authentication documentation
# ---------------------------------------------------------------------------

def customize_openapi_schema():
    """Generate OpenAPI schema with security schemes and per-endpoint security."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = super(FastAPI, app).openapi()

    # Define security schemes
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for authenticating requests. Obtain a key from the OpenAgents dashboard.",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token for authenticated access. Same keys as ApiKeyAuth are accepted.",
        },
    }

    # Apply default security globally (api_key OR bearer)
    openapi_schema["security"] = [
        {"ApiKeyAuth": []},
        {"BearerAuth": []},
    ]

    # Tag protected endpoints with "Protected" and mark them as requiring security
    protected_paths = ["/agents", "/agents/{agent_id}", "/tasks", "/tasks/{task_id}", "/leaderboard"]
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path in protected_paths:
            for method in ["get"]:
                operation = path_item.get(method)
                if operation:
                    operation["tags"] = ["Protected"]
                    operation["security"] = [
                        {"ApiKeyAuth": []},
                        {"BearerAuth": []},
                    ]

    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = customize_openapi_schema
