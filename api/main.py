"""
@fix-author rafaio1
@date 2026-08-20
@runtime os=linux, arch=x64, working_dir=/tmp/OpenAgents, shell=bash
@platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

import uuid
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .reputation import get_reputation, get_leaderboard as get_rep_leaderboard, update_on_completion

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
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


# --- Models ---

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


class ReputationResponse(BaseModel):
    agent_id: str
    score: int
    last_updated: int
    tasks_completed: int
    disputes: int


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
        raise AppException(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message="Agent not found",
            details={"agent_id": agent_id},
        )
    return agents_cache[agent_id]


@app.get("/agents/{agent_id}/reputation", response_model=ReputationResponse)
async def get_agent_reputation(agent_id: str):
    rep = get_reputation(agent_id)
    return rep


@app.post("/agents/{agent_id}/reputation/update")
async def update_agent_reputation(
    agent_id: str,
    success: bool = Query(...),
    completion_time_seconds: float = Query(0),
):
    rep = update_on_completion(agent_id, success, completion_time_seconds)
    return rep


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
        raise AppException(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message="Task not found",
            details={"task_id": task_id},
        )
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    # Use reputation system leaderboard if available, fallback to cache
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
    
    # Fallback to legacy cache-based leaderboard
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
