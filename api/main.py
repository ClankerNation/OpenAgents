"""
Contributor Metadata (required for bounty #41)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime
import uuid
import os
import time
import shutil
import psutil

# CORS configuration from environment
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
CORS_ALLOW_HEADERS = ["*"]

# Structured error response schema
ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "AUTH_FAILED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def make_error_response(status_code: int, message: str, details: Any = None, request_id: str = None):
    """Create a structured error response."""
    code = ERROR_CODES.get(status_code, "UNKNOWN_ERROR")
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        },
    )


app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate or accept X-Request-ID for log correlation."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    return make_error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        details={},
        request_id=request_id,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    details = {}
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        details[field] = error["msg"]
    return make_error_response(
        status_code=422,
        message="Validation error",
        details=details,
        request_id=request_id,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    return make_error_response(
        status_code=500,
        message="Internal server error",
        details={"type": type(exc).__name__},
        request_id=request_id,
    )


# Health check cache
_health_cache = {"timestamp": 0, "result": None}
_HEALTH_CACHE_TTL = 10  # seconds


async def _check_db() -> Dict:
    """Check database connectivity."""
    start = time.time()
    try:
        # Placeholder: in production, execute a simple query
        status = "healthy"
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": status, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}


async def _check_rpc() -> Dict:
    """Check RPC connectivity."""
    start = time.time()
    try:
        # Placeholder: in production, call eth_blockNumber
        status = "healthy"
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": status, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}


def _check_disk() -> Dict:
    """Check disk usage."""
    start = time.time()
    try:
        usage = shutil.disk_usage("/")
        used_percent = (usage.used / usage.total) * 100
        status = "healthy" if used_percent < 90 else "degraded"
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "status": status,
            "latency_ms": latency_ms,
            "used_percent": round(used_percent, 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}


def _check_memory() -> Dict:
    """Check memory usage."""
    start = time.time()
    try:
        mem = psutil.virtual_memory()
        status = "healthy" if mem.percent < 90 else "degraded"
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "status": status,
            "latency_ms": latency_ms,
            "used_percent": round(mem.percent, 2),
            "available_mb": round(mem.available / (1024 ** 2), 2),
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}


@app.get("/health")
async def health(request: Request):
    """Health check endpoint with component status."""
    now = time.time()

    # Check cache
    if _health_cache["result"] and (now - _health_cache["timestamp"]) < _HEALTH_CACHE_TTL:
        cached = _health_cache["result"]
        return JSONResponse(
            status_code=200 if cached["status"] == "healthy" else 503,
            content=cached,
        )

    # Run checks
    db_result = await _check_db()
    rpc_result = await _check_rpc()
    disk_result = _check_disk()
    memory_result = _check_memory()

    components = {
        "database": db_result,
        "rpc": rpc_result,
        "disk": disk_result,
        "memory": memory_result,
    }

    # Overall status reflects worst component
    statuses = [c["status"] for c in components.values()]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    result = {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "components": components,
    }

    # Cache result
    _health_cache["timestamp"] = now
    _health_cache["result"] = result

    status_code = 200 if overall == "healthy" else 503
    return JSONResponse(status_code=status_code, content=result)


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
