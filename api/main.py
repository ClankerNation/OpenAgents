// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Structured Error Response Schema
class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict = {}
    request_id: str

# Custom Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = str(uuid.uuid4())
    
    # Map status codes to error codes
    error_code_map = {
        400: "VALIDATION_ERROR",
        401: "AUTH_FAILED",
        403: "AUTH_FAILED",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
    }
    error_code = error_code_map.get(exc.status_code, "INTERNAL_ERROR")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": error_code,
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "details": {},
            "request_id": request_id,
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(uuid.uuid4())
    
    # Extract field-level validation details
    field_errors = {}
    for error in exc.errors():
        loc = ".".join(str(l) for l in error.get("loc", []))
        field_errors[loc] = error.get("msg", "Validation failed")
    
    return JSONResponse(
        status_code=400,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"fields": field_errors},
            "request_id": request_id,
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {"error_type": type(exc).__name__},
            "request_id": request_id,
        },
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
