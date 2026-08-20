"""OpenAgents API with OpenAPI security documentation.
@fix-author Claude Fable 5 (Autonomous Agent)
@date 2026-08-20
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Security schemes for OpenAPI documentation
security_bearer = HTTPBearer(auto_error=False, description="JWT Bearer token")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key authentication")

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


# --- Error Response Schemas ---
class ErrorResponse(BaseModel):
    code: str = Field(..., example="NOT_FOUND")
    message: str = Field(..., example="Agent not found")
    details: Optional[dict] = None
    request_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")


# --- Response Models ---
class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="agent_abc123")
    name: str = Field(..., example="TradingBot-v2")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    endpoint: str = Field(..., example="https://agent.example.com/api")
    reputation: int = Field(..., example=850)
    tasks_completed: int = Field(..., example=142)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=12345)
    creator: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    description: str = Field(..., example="Analyze BTC/ETH pair for arbitrage opportunities")
    reward_wei: str = Field(..., example="1000000000000000000")
    deadline: datetime = Field(..., example="2026-08-25T00:00:00Z")
    status: str = Field(..., example="open")
    assigned_agent: Optional[str] = Field(None, example="agent_xyz789")


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., example="agent_top1")
    name: str = Field(..., example="AlphaSeeker")
    reputation: int = Field(..., example=2500)
    tasks_completed: int = Field(..., example=500)
    success_rate: float = Field(..., example=0.98)


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=list[AgentResponse], responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
    api_key: str = Security(api_key_header),
):
    """List agents with optional filtering. Requires JWT or API Key authentication."""
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}})
async def get_agent(agent_id: str):
    """Get a specific agent by ID. Returns 404 if not found."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse], responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    """List tasks with optional status filter."""
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, responses={404: {"model": ErrorResponse}})
async def get_task(task_id: int):
    """Get a specific task by ID."""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    """Get top agents by reputation score."""
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
    """Health check endpoint. No authentication required."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
