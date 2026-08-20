# @contributor-info rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

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

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token for authenticated requests")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API key for programmatic access")


async def verify_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
):
    """Verify either JWT Bearer or API Key is present."""
    if credentials or api_key:
        return {"authenticated": True}
    return {"authenticated": False}


class ErrorResponse(BaseModel):
    code: str = Field(..., example="VALIDATION_ERROR")
    message: str = Field(..., example="Invalid request parameters")
    details: Optional[dict] = Field(None, example={"field": "limit", "error": "must be <= 100"})
    request_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")


class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="0xabc123...")
    name: str = Field(..., example="TradingBot-v2")
    owner: str = Field(..., example="0xdef456...")
    endpoint: str = Field(..., example="https://agent.example.com/api")
    reputation: int = Field(..., example=85)
    tasks_completed: int = Field(..., example=42)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=1234)
    creator: str = Field(..., example="0xdef456...")
    description: str = Field(..., example="Analyze market data for Q3 report")
    reward_wei: str = Field(..., example="1000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="open")
    assigned_agent: Optional[str] = Field(None, example="0xabc123...")


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., example="0xabc123...")
    name: str = Field(..., example="TradingBot-v2")
    reputation: int = Field(..., example=85)
    tasks_completed: int = Field(..., example=42)
    success_rate: float = Field(..., example=0.95)


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get(
    "/agents",
    response_model=list[AgentResponse],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate Limited"},
    },
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def list_agents(
    active_only: bool = Query(True, description="Filter to active agents only"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    auth=Depends(verify_auth),
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
        404: {"model": ErrorResponse, "description": "Agent not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate Limited"},
    },
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def get_agent(agent_id: str, auth=Depends(verify_auth)):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get(
    "/tasks",
    response_model=list[TaskResponse],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate Limited"},
    },
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    auth=Depends(verify_auth),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        429: {"model": ErrorResponse, "description": "Rate Limited"},
    },
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def get_task(task_id: int, auth=Depends(verify_auth)):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        429: {"model": ErrorResponse, "description": "Rate Limited"},
    },
)
async def leaderboard(limit: int = Query(20, ge=1, le=50, description="Number of top agents")):
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
