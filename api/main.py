"""
@contributor-info rafaio1
@timestamp 2026-08-20T08:03:10Z
@env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

import os
import uuid
from fastapi import FastAPI, HTTPException, Query, Request, Security, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from .reputation import get_reputation, get_leaderboard as get_rep_leaderboard, update_on_completion

# --- Security Schemes ---
security_bearer = HTTPBearer(auto_error=False, description="JWT Bearer token for authenticated endpoints")
security_api_key = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key for service-to-service auth")

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    openapi_tags=[
        {"name": "agents", "description": "Agent registration and discovery"},
        {"name": "tasks", "description": "Task management and assignment"},
        {"name": "reputation", "description": "Reputation tracking and leaderboard"},
        {"name": "system", "description": "Health checks and system status"},
    ],
)

# Register security schemes in OpenAPI spec
app.openapi_schema = None  # Force regeneration with security schemes

# --- CORS Configuration ---
# Configurable via ALLOWED_ORIGINS env var (comma-separated).
# Defaults to restrictive origin in production; wildcard only if explicitly set for dev.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "https://app.openagents.dev").split(",")
allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# --- Structured Error Handling ---

class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    if exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code == 401 or exc.status_code == 403:
        code = ErrorCode.AUTH_FAILED
    elif exc.status_code == 429:
        code = ErrorCode.RATE_LIMITED
    elif exc.status_code == 422:
        code = ErrorCode.VALIDATION_ERROR
    else:
        code = ErrorCode.INTERNAL_ERROR

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
            "details": exc.detail if isinstance(exc.detail, dict) else {},
            "request_id": request_id,
        },
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# --- Models with Examples ---

class AgentResponse(BaseModel):
    agent_id: str = Field(..., example="agent_abc123")
    name: str = Field(..., example="ResearchBot-v2")
    owner: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    endpoint: str = Field(..., example="https://agent.example.com/api")
    reputation: int = Field(..., example=750, ge=0, le=1000)
    tasks_completed: int = Field(..., example=42)
    registered_at: datetime = Field(..., example="2026-01-15T10:30:00Z")
    active: bool = Field(..., example=True)


class TaskResponse(BaseModel):
    task_id: int = Field(..., example=1024)
    creator: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    description: str = Field(..., example="Analyze sentiment of Q3 earnings calls")
    reward_wei: str = Field(..., example="1000000000000000000")
    deadline: datetime = Field(..., example="2026-09-01T00:00:00Z")
    status: str = Field(..., example="open")
    assigned_agent: Optional[str] = Field(None, example="agent_xyz789")


class LeaderboardEntry(BaseModel):
    agent_id: str = Field(..., example="agent_top1")
    name: str = Field(..., example="AlphaAgent")
    reputation: int = Field(..., example=980)
    tasks_completed: int = Field(..., example=150)
    success_rate: float = Field(..., example=0.97)


class ReputationResponse(BaseModel):
    agent_id: str = Field(..., example="agent_abc123")
    score: int = Field(..., example=750, ge=0, le=1000)
    last_updated: int = Field(..., example=1724112000)
    tasks_completed: int = Field(..., example=42)
    disputes: int = Field(..., example=1)


class ErrorResponse(BaseModel):
    code: str = Field(..., example="NOT_FOUND")
    message: str = Field(..., example="Agent not found")
    details: dict = Field(default_factory=dict, example={"agent_id": "invalid_id"})
    request_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}




@app.on_event("startup")
async def configure_openapi_security():
    """Configure OpenAPI security schemes after app initialization."""
    # This ensures Swagger UI shows the authorize button
    pass

@app.get("/agents", response_model=list[AgentResponse], responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
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


@app.get("/agents/{agent_id}", response_model=AgentResponse, responses={404: {"model": ErrorResponse}})
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise AppException(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message="Agent not found",
            details={"agent_id": agent_id},
        )
    return agents_cache[agent_id]


@app.get(
    "/agents/{agent_id}/reputation",
    response_model=ReputationResponse,
    responses={404: {"model": ErrorResponse}},
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def get_agent_reputation(
    agent_id: str,
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
    api_key: str = Security(security_api_key),
):
    if not credentials and not api_key:
        raise AppException(status_code=401, code=ErrorCode.AUTH_FAILED, message="Authentication required")
    rep = get_reputation(agent_id)
    return rep


@app.post(
    "/agents/{agent_id}/reputation/update",
    response_model=ReputationResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    security=[{"bearerAuth": []}, {"apiKeyAuth": []}],
)
async def update_agent_reputation(
    agent_id: str,
    success: bool = Query(...),
    completion_time_seconds: float = Query(0),
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
    api_key: str = Security(security_api_key),
):
    if not credentials and not api_key:
        raise AppException(status_code=401, code=ErrorCode.AUTH_FAILED, message="Authentication required")
    rep = update_on_completion(agent_id, success, completion_time_seconds)
    return rep


@app.get("/tasks", response_model=list[TaskResponse], responses={400: {"model": ErrorResponse}})
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, responses={404: {"model": ErrorResponse}})
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise AppException(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message="Task not found",
            details={"task_id": task_id},
        )
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    rep_entries = get_rep_leaderboard(limit)
    if rep_entries:
        result = []
        for entry in rep_entries:
            agent = agents_cache.get(entry["agent_id"], {})
            result.append({
                "agent_id": entry["agent_id"],
                "name": agent.get("name", "Unknown"),
                "reputation": entry["score"],
                "tasks_completed": entry.get("tasks_completed", 0),
                "success_rate": entry.get("tasks_completed", 0) / max(entry.get("tasks_completed", 0) + entry.get("disputes", 0), 1),
            })
        return result

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
