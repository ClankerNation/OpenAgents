from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

import os
import shutil
import time

from .models.database import engine

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


class ComponentHealth(BaseModel):
    status: str
    latency_ms: float
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    components: Dict[str, ComponentHealth]
    agents_indexed: int = 0
    tasks_indexed: int = 0
    cached: bool = False


agents_cache: dict = {}
tasks_cache: dict = {}

_health_cache: dict = {}
_health_cache_ts: float = 0.0
_HEALTH_CACHE_TTL = 10


def _check_db() -> ComponentHealth:
    start = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="healthy", latency_ms=round(latency, 2), detail="SELECT 1 ok")
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="unhealthy", latency_ms=round(latency, 2), detail=f"DB connection failed: {e}")


def _check_disk() -> ComponentHealth:
    start = time.monotonic()
    try:
        usage = shutil.disk_usage(os.getcwd())
        free_pct = (usage.free / usage.total) * 100
        latency = (time.monotonic() - start) * 1000
        if free_pct < 5:
            status = "unhealthy"
        elif free_pct < 15:
            status = "degraded"
        else:
            status = "healthy"
        return ComponentHealth(status=status, latency_ms=round(latency, 2), detail=f"{free_pct:.1f}% free ({usage.free // (1024**3)}GB / {usage.total // (1024**3)}GB)")
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="unhealthy", latency_ms=round(latency, 2), detail=str(e))


def _check_memory() -> ComponentHealth:
    start = time.monotonic()
    try:
        import psutil
        mem = psutil.virtual_memory()
        latency = (time.monotonic() - start) * 1000
        if mem.percent > 95:
            status = "unhealthy"
        elif mem.percent > 85:
            status = "degraded"
        else:
            status = "healthy"
        return ComponentHealth(status=status, latency_ms=round(latency, 2), detail=f"{mem.percent}% used ({mem.available // (1024**2)}MB available)")
    except ImportError:
        latency = (time.monotonic() - start) * 1000
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            total = int(lines[0].split()[1])
            available = int(lines[2].split()[1])
            pct = ((total - available) / total) * 100
            if pct > 95:
                status = "unhealthy"
            elif pct > 85:
                status = "degraded"
            else:
                status = "healthy"
            return ComponentHealth(status=status, latency_ms=round(latency, 2), detail=f"{pct:.1f}% used (/proc/meminfo)")
        except Exception:
            return ComponentHealth(status="healthy", latency_ms=round(latency, 2), detail="psutil not installed, /proc unavailable")
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="unhealthy", latency_ms=round(latency, 2), detail=str(e))


def _check_rpc() -> ComponentHealth:
    start = time.monotonic()
    rpc_url = os.getenv("RPC_URL")
    if not rpc_url:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="healthy", latency_ms=round(latency, 2), detail="RPC_URL not configured")
    try:
        import urllib.request
        import json
        req = urllib.request.Request(rpc_url, data=json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        latency = (time.monotonic() - start) * 1000
        if "result" in data:
            return ComponentHealth(status="healthy", latency_ms=round(latency, 2), detail=f"block={int(data['result'], 16)}")
        return ComponentHealth(status="degraded", latency_ms=round(latency, 2), detail="RPC returned no result")
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(status="unhealthy", latency_ms=round(latency, 2), detail=str(e))


def _worst_status(components: dict) -> str:
    order = {"healthy": 0, "degraded": 1, "unhealthy": 2}
    worst = "healthy"
    for comp in components.values():
        if order.get(comp.status, 2) > order.get(worst, 0):
            worst = comp.status
    return worst


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


@app.get("/health", response_model=HealthResponse)
async def health(response: Response):
    global _health_cache, _health_cache_ts

    now = time.monotonic()
    if _health_cache and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        cached = HealthResponse(**_health_cache)
        cached.cached = True
        return cached

    components = {
        "database": _check_db(),
        "disk": _check_disk(),
        "memory": _check_memory(),
        "rpc": _check_rpc(),
    }
    result = HealthResponse(
        status=_worst_status(components),
        components=components,
        agents_indexed=len(agents_cache),
        tasks_indexed=len(tasks_cache),
    )
    _health_cache = result.model_dump()
    _health_cache_ts = now

    if result.status == "unhealthy":
        response.status_code = 503

    return result
