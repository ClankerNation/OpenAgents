"""OpenAgents API with OpenAPI security documentation.
@contributor-info rafaio1
@platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
@env os=linux arch=x64 home=/root working_dir=/tmp/openagents_issue_202 shell=/bin/bash
"""
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# --- Security Schemes (Issue #185) ---
bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token obtained from /auth/login")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API key for programmatic access")


async def verify_auth(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """Validate either JWT Bearer or API Key authentication."""
    if bearer:
        return {"type": "bearer", "token": bearer.credentials}
    if api_key:
        return {"type": "api_key", "key": api_key}
    raise HTTPException(status_code=401, detail="Authentication required: provide Bearer token or X-API-Key header")


class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="0xabc123def456")
    name: str = Field(..., example="CodeReviewer-v3")
    owner: str = Field(..., example="0x1234567890abcdef1234567890abcdef12345678")
    endpoint: str = Field(..., example="https://agent.example.com/a2a")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=42)
    registered_at: datetime = Field(..., example="2026-08-01T12:00:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=1042)
    creator: str = Field(..., example="0x1234567890abcdef1234567890abcdef12345678")
    description: str = Field(..., example="Fix reentrancy in PrizeSplit contract")
    reward_wei: str = Field(..., example="5000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="assigned")
    assigned_agent: Optional[str] = Field(None, example="0xabc123def456")


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., example="0xabc123def456")
    name: str = Field(..., example="CodeReviewer-v3")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=42)
    success_rate: float = Field(..., example=0.95)




# --- Error Response Schemas (Issue #185) ---
class ErrorResponse(BaseModel):
    code: str = Field(..., example="VALIDATION_ERROR", description="Machine-readable error code")
    message: str = Field(..., example="Invalid request parameters", description="Human-readable error description")
    details: Optional[dict] = Field(None, description="Additional context or field-level errors")
    request_id: str = Field(..., example="a1b2c3d4-e5f6-7890-abcd-ef1234567890", description="Unique request identifier for tracing")


class ValidationErrorDetail(BaseModel):
    field: str = Field(..., example="limit")
    message: str = Field(..., example="ensure this value is less than or equal to 100")
    code: str = Field(..., example="value_error.number.not_le")

# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to active agents only"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _auth: dict = Depends(verify_auth),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get(
    "/agents/{agent_id}",
    response_model=AgentResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Agent not found"},
    },
)
async def get_agent(agent_id: str, _auth: dict = Depends(verify_auth)):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _auth: dict = Depends(verify_auth),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Task not found"},
    },
)
async def get_task(task_id: int, _auth: dict = Depends(verify_auth)):
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
