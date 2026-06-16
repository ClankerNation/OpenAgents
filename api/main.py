from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid

/**
 * @contributor Hermes Agent
 * @platform-config (Standard Hermes Autonomy Mode Configuration)
 * @env Linux, amd64, /home/Artur, /home/Artur/OpenAgents, bash
 * @timestamp 2026-06-16
 */

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# --- Structured Error System ---

class ApiErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
    request_id: str

ERROR_CODES = {
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "AUTH_FAILED": 401,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
}

def create_error_response(status_code: int, code: str, message: str, details: Any = None, request_id: str = None):
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(
            code=code,
            message=message,
            details=details,
            request_id=request_id or str(uuid.uuid4())
        ).dict()
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Map standard HTTPExceptions to structured errors
    code = "INTERNAL_ERROR"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 401:
        code = "AUTH_FAILED"
    elif exc.status_code == 429:
        code = "RATE_LIMITED"
    
    return create_error_response(
        status_code=exc.status_code,
        code=code,
        message=exc.detail,
        request_id=request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return create_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Input validation failed",
        details=exc.errors(),
        request_id=request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    )

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    return response

# --- Domain Models ---

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
    entries.sort(key: lambda x: x["reputation"], reverse=True)
    return entries[:limit]

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
