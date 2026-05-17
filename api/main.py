"""
@fix-author: metatron-hermes-agent
@fix-date: 2026-05-17T04:25:00Z
@fix-issue: #202 — Add structured error responses with error codes
@pre-conversation:
  Identity: Metatron (AI — celestial scribe, autonomous coding agent)
  Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro
  Environment: linux, x86_64, /home/power, /home/power/repos/OpenAgents, bash
  Operating Instructions (SOUL.md excerpt):
    - Be genuinely helpful, not performatively helpful
    - Have opinions. Be resourceful before asking.
    - Earn trust through competence. Remember you're a guest.
    - Private things stay private. Period.
    - Each session, you wake up fresh. These files are your memory.
    - Running as scheduled cron job. No user present.
    - Execute task fully and autonomously.
  Tools: terminal, file, web, search, browser, skills, execute_code
  Skills loaded: github-bounties, github-pr-workflow, agent-opportunity-scanning
@runtime:
  os: linux
  arch: x86_64
  home_dir: /home/power
  working_dir: /home/power/repos/OpenAgents
  shell: bash
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


# ─── Error Schema ────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Field-level validation error details."""
    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    """Standardized API error response."""
    code: str
    message: str
    details: Optional[Any] = None
    request_id: str
    timestamp: str


# ─── Request ID Middleware ───────────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a unique request_id to every request for error tracing."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Exception Handlers ──────────────────────────────────────────

def _get_request_id(request: Optional[Request]) -> str:
    if request and hasattr(request.state, "request_id"):
        return request.state.request_id
    return str(uuid.uuid4())


def _status_to_code(status_code: int) -> str:
    """Map HTTP status codes to consistent error codes."""
    mapping = {
        400: "VALIDATION_ERROR",
        401: "AUTH_FAILED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "INTERNAL_ERROR",
        503: "INTERNAL_ERROR",
    }
    return mapping.get(status_code, "INTERNAL_ERROR")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = _status_to_code(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=code,
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            request_id=_get_request_id(request),
            timestamp=datetime.utcnow().isoformat() + "Z",
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(
            field=" -> ".join(str(loc) for loc in err["loc"]),
            message=err["msg"],
            type=err["type"],
        )
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=[d.model_dump() for d in details],
            request_id=_get_request_id(request),
            timestamp=datetime.utcnow().isoformat() + "Z",
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"type": type(exc).__name__} if app.debug else None,
            request_id=_get_request_id(request),
            timestamp=datetime.utcnow().isoformat() + "Z",
        ).model_dump(),
    )


# ─── Response Models ─────────────────────────────────────────────

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
