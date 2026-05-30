# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:45:50+07:00

import uuid
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .routes import agents, tasks, payments, admin
from .models.database import init_db
from .middleware.request_id import RequestIDMiddleware
from .middleware.ratelimit import RateLimitMiddleware

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Register middlewares in correct order
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)

# Helper for structured error responses
def create_error_response(request: Request, code: str, message: str, details: dict, status_code: int, headers: dict = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

    content = {
        "code": code,
        "message": message,
        "details": details,
        "request_id": request_id
    }
    
    response_headers = {"X-Request-ID": request_id}
    if headers:
        response_headers.update(headers)
        
    return JSONResponse(status_code=status_code, content=content, headers=response_headers)

# Custom exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        field = ".".join(str(x) for x in loc)
        details[field] = error.get("msg", "Validation error")
    
    return create_error_response(request, "VALIDATION_ERROR", "Validation failed", details, 422)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    status_code = exc.status_code
    if status_code == 404:
        code = "NOT_FOUND"
    elif status_code in (401, 403):
        code = "AUTH_FAILED"
    elif status_code == 429:
        code = "RATE_LIMITED"
    elif status_code == 500:
        code = "INTERNAL_ERROR"
    else:
        code = f"HTTP_{status_code}"
    
    headers = {}
    if hasattr(exc, "headers") and exc.headers:
        headers.update(exc.headers)
        
    return create_error_response(request, code, exc.detail, {}, status_code, headers=headers)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    message = str(exc) or "Internal server error"
    return create_error_response(request, "INTERNAL_ERROR", message, {}, 500)

# Register routers
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(payments.router)
app.include_router(admin.router)

# Extra test routes for testing specific error responses
@app.get("/test-error/500")
async def trigger_500():
    raise Exception("Test internal server error")

@app.get("/test-error/429")
async def trigger_429():
    raise HTTPException(status_code=429, detail="Test rate limit exceeded")

@app.on_event("startup")
def on_startup():
    init_db()


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
