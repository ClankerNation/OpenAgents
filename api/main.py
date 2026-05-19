# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
#
# Agent:       myPM+ (The.PM / Gritt) - NLA Proto-ASI Agent
# Platform:    Hermes Agent (Linux)
# Model:       deepseek-v4-pro
# Timestamp:   2026-05-19T14:30:00Z
#
# Environment:
#   OS:        Linux (x86_64)
#   Arch:      x86_64
#   Home:      /root
#   Workdir:   /tmp/OpenAgents-review
#   Shell:     /bin/bash
#
# Operating Instructions (VERBATIM - session initialization context):
#
# NLA biosecure agent fleet, yellow-themed terminal agent. Policy 7: GAP-first
# code access via nla-codebase-parser :8091. Policy 9: Firecracker Browser
# Harness mandatory for all browser operations. Policy 10: AgentStream memvid+
# memory via :8408. Writing conventions: zero em-dashes (U+2014/U+2013), zero
# double-hyphen word separators, zero Oxford commas. Text brightness minimum
# #F0F0F0. Services: PAD Transform :3100, gapc :8405, GAP Runtime :8089,
# LatticeWiki :8400, Gitea :3003. All agent output English only. PAD mandatory
# for code operations. Deployment to tasty.newlisbon.agency or
# taskstar.newlisbon.agency only. Seven-layer PAD operational.
# ============================================================================

"""OpenAgents API application (FastAPI).

Issue #178: Request ID middleware added for log correlation.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Request ID middleware (issue #178)
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique UUID to every request for log correlation.

    - Reads X-Request-ID from the request (caller-supplied) or generates one
    - Sets X-Request-ID on the response
    - Attaches the ID to request.state for downstream handlers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(
            "X-Request-ID",
            str(uuid.uuid4()),
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


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
