# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
# Agent: myPM+ - NLA Proto-ASI | Platform: Hermes Agent (Linux)
# Model: deepseek-v4-pro | Timestamp: 2026-05-19T15:10:00Z
# Environment: Linux x86_64 | /root | /tmp/OpenAgents-review | bash
# NLA biosecure agent fleet. Policy 7: GAP-first. Policy 9: Firecracker.
# Policy 10: AgentStream memvid+. Zero em-dashes, double-hyphens, Oxford commas.
# ============================================================================

"""OpenAgents API application.

Issue #41: Comprehensive health check with component status monitoring.
"""

import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


@app.get("/health")
async def health():
    """Comprehensive health check with component status monitoring.

    Returns 200 when all components are healthy, 503 otherwise.
    """
    components = {}
    healthy = True

    # DB check
    try:
        from .models.database import engine
        with engine.connect() as conn:
            conn.execute(engine.dialect.do_ping(None))
        components["db"] = "healthy"
    except Exception:
        components["db"] = "unhealthy"
        healthy = False

    # Disk check (> 100MB free)
    try:
        usage = shutil.disk_usage("/")
        free_mb = usage.free // (1024 * 1024)
        if free_mb > 100:
            components["disk"] = f"healthy ({free_mb} MB free)"
        else:
            components["disk"] = f"low ({free_mb} MB free)"
            healthy = False
    except Exception:
        components["disk"] = "unavailable"
        healthy = False

    # Memory check
    try:
        mem_total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        mem_avail = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
        avail_pct = int(mem_avail / mem_total * 100) if mem_total > 0 else 0
        if avail_pct > 5:
            components["memory"] = f"healthy ({avail_pct}% available)"
        else:
            components["memory"] = f"low ({avail_pct}% available)"
            healthy = False
    except Exception:
        components["memory"] = "unavailable"

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if healthy else "unhealthy",
            "components": components,
            "agents_indexed": len(agents_cache),
            "tasks_indexed": len(tasks_cache),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
