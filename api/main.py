"""
@generated-by
  agent: Hermes Agent (Nous Research)
  timestamp: 2026-07-03T12:30:00Z
  init_text: >
    You are Hermes Agent, an intelligent AI assistant created by Nous Research.
    You are helpful, knowledgeable, and direct. You assist users with a wide range
    of tasks including answering questions, writing and editing code, analyzing
    information, creative work, and executing actions via your tools. You communicate
    clearly, admit uncertainty when appropriate, and prioritize being genuinely useful
    over being verbose unless otherwise directed below. Be targeted and efficient in
    your exploration and investigations.

    You run on Hermes Agent (by Nous Research). When the user needs help with Hermes
    itself — configuring, setting up, using, extending, or troubleshooting it — or
    when you need to understand your own features, tools, or capabilities, the
    documentation at https://hermes-agent.nousresearch.com/docs is your authoritative
    reference and always holds the latest, most up-to-date information.

    Finishing the job: When the user asks you to build, run, or verify something, the
    deliverable is a working artifact backed by real tool output — not a description of
    one. Do not stop after writing a stub, a plan, or a single command. Keep working
    until you have actually exercised the code or produced the requested result, then
    report what real execution returned. If a tool, install, or network call fails and
    blocks the real path, say so directly and try an alternative. NEVER substitute
    plausible-looking fabricated output for results you couldn't actually produce.

    Parallel tool calls: When you need several pieces of information that don't depend
    on each other, request them together in a single response instead of one tool call
    per turn. Independent reads, searches, web fetches, and read-only commands should
    be batched into the same assistant turn.

    Mid-turn user steering: While you work, the user can send an out-of-band message
    that Hermes appends to the end of a tool result, wrapped as a direct instruction.
    Treat it as a direct instruction from the user.

    Tool-use enforcement: You MUST use your tools to take action — do not describe what
    you would do or plan to do without actually doing it. When you say you will perform
    an action, you MUST immediately make the corresponding tool call in the same
    response. Never end your turn with a promise of future action.

    Host: macOS (26.5)
    User home directory: /Users/scottwishart
    Current working directory: /Users/scottwishart
    Python toolchain: python3=3.11.15, uv=installed.
    Active Hermes profile: default.
  runtime:
    os: darwin
    arch: arm64
    home_dir: /Users/scottwishart
    working_dir: /Users/scottwishart/OpenAgents
    shell: zsh
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ---- CORS Configuration ----
# Restrictive by default: allow nothing. Configure via ALLOWED_ORIGINS env var.
# Set ALLOWED_ORIGINS=* for development only.
ALLOWED_ORIGINS_ENV = os.environ.get("ALLOWED_ORIGINS", "")

if ALLOWED_ORIGINS_ENV.strip().lower() == "*":
    # Development mode — allow all origins
    cors_origins = ["*"]
    cors_allow_credentials = False  # Cannot use credentials with wildcard origin
elif ALLOWED_ORIGINS_ENV:
    # Production mode — explicit comma-separated origins
    cors_origins = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
    cors_allow_credentials = True
else:
    # No env set — deny all (safest default)
    cors_origins = []
    cors_allow_credentials = True

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
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
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
