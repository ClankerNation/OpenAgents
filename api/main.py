from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# @fix-author rafaio1
# @date 2026-08-25T00:00:00Z
# @runtime linux x64 /tmp/openagents_issue_202 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


class ErrorResponse(BaseModel):
    """Standardized error response structure for all API endpoints."""
    error_code: str
    message: str
    details: Optional[dict] = None
    timestamp: str


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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Global handler to convert HTTPExceptions into structured error responses."""
    # Map status codes to semantic error codes
    error_code_map = {
        400: "INVALID_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    
    error_code = error_code_map.get(exc.status_code, "UNKNOWN_ERROR")
    
    # Extract specific error codes from detail if provided as dict
    detail = exc.detail
    if isinstance(detail, dict):
        error_code = detail.get("error_code", error_code)
        message = detail.get("message", str(exc.detail))
        extra_details = {k: v for k, v in detail.items() if k not in ("error_code", "message")}
    else:
        message = str(detail)
        extra_details = None
    
    response = ErrorResponse(
        error_code=error_code,
        message=message,
        details=extra_details,
        timestamp=datetime.utcnow().isoformat(),
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


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
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "message": f"Agent with ID '{agent_id}' does not exist",
                "agent_id": agent_id,
            },
        )
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    valid_statuses = {"open", "assigned", "completed", "disputed", "cancelled"}
    if status and status.lower() not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_TASK_STATUS",
                "message": f"Invalid status filter. Must be one of: {', '.join(sorted(valid_statuses))}",
                "provided_status": status,
                "valid_statuses": sorted(list(valid_statuses)),
            },
        )
    
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "TASK_NOT_FOUND",
                "message": f"Task with ID {task_id} does not exist",
                "task_id": task_id,
            },
        )
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
