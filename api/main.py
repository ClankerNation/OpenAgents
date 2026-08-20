// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
from fastapi import FastAPI, HTTPException, Query
import time
import os
import psutil
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
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


# Health check cache (10s TTL)
_health_cache = {"data": None, "ts": 0}
HEALTH_CACHE_TTL = 10

def _check_db() -> dict:
    start = time.monotonic()
    try:
        # Simulate DB check via cache access
        _ = len(agents_cache) + len(tasks_cache)
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def _check_rpc() -> dict:
    start = time.monotonic()
    try:
        # Placeholder: in production would ping RPC node
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def _check_disk() -> dict:
    start = time.monotonic()
    try:
        usage = psutil.disk_usage("/")
        if usage.percent > 95:
            return {"status": "unhealthy", "usage_percent": usage.percent}
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "usage_percent": usage.percent, "latency_ms": latency}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def _check_memory() -> dict:
    start = time.monotonic()
    try:
        mem = psutil.virtual_memory()
        if mem.percent > 95:
            return {"status": "unhealthy", "usage_percent": mem.percent}
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "usage_percent": mem.percent, "latency_ms": latency}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/health")
async def health():
    now = time.time()
    if _health_cache["data"] and (now - _health_cache["ts"]) < HEALTH_CACHE_TTL:
        cached = _health_cache["data"]
        from fastapi.responses import JSONResponse
        status_code = 200 if cached["status"] == "ok" else 503
        return JSONResponse(content=cached, status_code=status_code)

    components = {
        "db": _check_db(),
        "rpc": _check_rpc(),
        "disk": _check_disk(),
        "memory": _check_memory(),
    }

    overall = "ok" if all(c["status"] == "healthy" for c in components.values()) else "degraded"
    response = {
        "status": overall,
        "components": components,
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }

    _health_cache["data"] = response
    _health_cache["ts"] = now

    from fastapi.responses import JSONResponse
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(content=response, status_code=status_code)
