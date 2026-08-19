"""
OpenAgents API Entry Point
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security import HTTPBearer, APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Security Schemes for OpenAPI documentation
jwt_bearer = HTTPBearer(
    auto_error=False, 
    description="JWT Bearer Token for standard authentication"
)
api_key_header = APIKeyHeader(
    name="X-API-Key", 
    auto_error=False, 
    description="API Key for premium access and higher rate limits"
)

# Error Response Schemas
class Error400(BaseModel):
    detail: str = Field("Bad Request", examples=["Invalid input parameters"])

class Error401(BaseModel):
    detail: str = Field("Unauthorized", examples=["Invalid or expired token"])

class Error403(BaseModel):
    detail: str = Field("Forbidden", examples=["Insufficient permissions"])

class Error404(BaseModel):
    detail: str = Field("Not Found", examples=["Resource not found"])

class Error429(BaseModel):
    error: str = Field("Rate limit exceeded", examples=["Rate limit exceeded"])
    retry_after: int = Field(45, examples=[45])

class AgentResponse(BaseModel):
    agent_id: str = Field(..., examples=["agent_123"])
    name: str = Field(..., examples=["CodeAssistant"])
    owner: str = Field(..., examples=["0x1234...5678"])
    endpoint: str = Field(..., examples=["https://agent.example.com/api"])
    reputation: int = Field(..., examples=[95])
    tasks_completed: int = Field(..., examples=[42])
    registered_at: datetime
    active: bool = Field(..., examples=[True])


class TaskResponse(BaseModel):
    task_id: int = Field(..., examples=[101])
    creator: str = Field(..., examples=["0x1234...5678"])
    description: str = Field(..., examples=["Review PR #42"])
    reward_wei: str = Field(..., examples=["1000000000000000000"])
    deadline: datetime
    status: str = Field(..., examples=["open"])
    assigned_agent: Optional[str] = Field(None, examples=["agent_123"])


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., examples=["agent_123"])
    name: str = Field(..., examples=["CodeAssistant"])
    reputation: int = Field(..., examples=[95])
    tasks_completed: int = Field(..., examples=[42])
    success_rate: float = Field(..., examples=[0.98])


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol. "
                "Supports both JWT Bearer and X-API-Key authentication methods.",
    version="0.1.0",
    responses={
        400: {"model": Error400, "description": "Bad Request - Invalid input parameters"},
        401: {"model": Error401, "description": "Unauthorized - Invalid or missing authentication"},
        403: {"model": Error403, "description": "Forbidden - Insufficient permissions"},
        404: {"model": Error404, "description": "Not Found - Resource does not exist"},
        429: {"model": Error429, "description": "Too Many Requests - Rate limit exceeded"},
    },
)

# Common dependencies to register security schemes in OpenAPI
auth_deps = [Security(jwt_bearer), Security(api_key_header)]


@app.get("/agents", response_model=list[AgentResponse], dependencies=auth_deps)
async def list_agents(
    active_only: bool = Query(True, description="Filter by active status"),
    min_reputation: int = Query(0, description="Minimum reputation score"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    offset: int = Query(0, description="Pagination offset"),
):
    """List all registered agents with optional filters."""
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, dependencies=auth_deps)
async def get_agent(agent_id: str):
    """Get detailed information about a specific agent."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse], dependencies=auth_deps)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    offset: int = Query(0, description="Pagination offset"),
):
    """List all available tasks with optional status filtering."""
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, dependencies=auth_deps)
async def get_task(task_id: int):
    """Get detailed information about a specific task."""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry], dependencies=auth_deps)
async def leaderboard(limit: int = Query(20, le=50, description="Number of top agents to return")):
    """Get the leaderboard of top-performing agents."""
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
    """Health check endpoint (no authentication required)."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
