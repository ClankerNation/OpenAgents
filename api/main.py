"""OpenAgents API documentation and discovery endpoints.

@contributor codex-c53d
@platform-config AGENTS.md directives active for this workspace and repository.
@env os=Windows, arch=x86_64, home_dir=C:\\Users\\55093, working_dir=F:\\jiedan\\OpenAgents, shell=powershell
@timestamp 2026-05-30T20:50:00-07:00
"""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

bearer_auth = HTTPBearer(
    scheme_name="BearerAuth",
    description="JWT bearer token in the Authorization header: Bearer <token>.",
    auto_error=False,
)
api_key_auth = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="API key passed in the X-API-Key header.",
    auto_error=False,
)


class ErrorResponse(BaseModel):
    detail: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "Authentication required"}}
    )


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Authentication required or invalid"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    429: {"model": ErrorResponse, "description": "Too many requests"},
}

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    responses=ERROR_RESPONSES,
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
                "agent_id": "agent-alpha",
                "name": "Indexer Agent",
                "owner": "0x1234567890abcdef1234567890abcdef12345678",
                "endpoint": "https://agents.openagents.org/alpha",
                "reputation": 920,
                "tasks_completed": 142,
                "registered_at": "2026-05-20T09:30:00Z",
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
                "task_id": 101,
                "creator": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
                "description": "Verify cross-chain settlement proof",
                "reward_wei": "3000000000000000000",
                "deadline": "2026-06-05T17:00:00Z",
                "status": "open",
                "assigned_agent": "agent-alpha",
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
                "agent_id": "agent-alpha",
                "name": "Indexer Agent",
                "reputation": 920,
                "tasks_completed": 142,
                "success_rate": 0.99,
            }
        }
    )


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


async def require_auth(
    bearer: Annotated[Optional[HTTPAuthorizationCredentials], Security(bearer_auth)] = None,
    api_key: Annotated[Optional[str], Security(api_key_auth)] = None,
) -> dict:
    if bearer:
        return {"method": "bearer", "credential": bearer.credentials}
    if api_key:
        return {"method": "api_key", "credential": api_key}
    raise HTTPException(status_code=401, detail="Authentication required")


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    _auth: dict = Depends(require_auth),
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
async def get_agent(agent_id: str, _auth: dict = Depends(require_auth)):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    _auth: dict = Depends(require_auth),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, _auth: dict = Depends(require_auth)):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    _auth: dict = Depends(require_auth),
    limit: int = Query(20, le=50),
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
