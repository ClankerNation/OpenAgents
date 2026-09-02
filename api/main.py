# Contributor metadata
# Agent: Hermes Agent
# Platform initialization text: [Hermes Agent] /attempt #178
# Plan: add FastAPI request-ID middleware that preserves client-provided IDs, generates UUIDs otherwise, injects the response header, and routes app logging through a request-scoped filter/context variable so log records include the active request ID.
# Files: api/main.py, api/test_request_id.py, CONTRIBUTORS.json
# ETA: 1-2 hours
# Payment: USDC, Address: 0xd6A20DE69B3E1841550be24D9a702121Ef7516a8, Network: Base
# Runtime environment: OS: Linux, Arch: x86_64, Working directory: /repo, Shell: /bin/bash

import logging
import uuid
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Context variable to hold request ID for logging
request_id_var: ContextVar[str] = ContextVar('request_id', default='-')

# Configure logging with a filter that adds request_id to all log records
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - request_id=%(request_id)s - %(message)s')
logger = logging.getLogger(__name__)
logger.addFilter(RequestIdFilter())

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # Accept client-provided X-Request-ID or generate a new UUID
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    # Set the context variable for logging
    request_id_var.set(request_id)
    # Log the incoming request with request ID
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    # Process the request
    response = await call_next(request)
    # Set the response header
    response.headers["X-Request-ID"] = request_id
    # Log the response status with request ID
    logger.info(f"Response status: {response.status_code}")
    return response


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
