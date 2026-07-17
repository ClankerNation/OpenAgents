# @contributor ahmedabdelkarim504-commits
# @platform-config Agent protocol: Read Brain Home.md first. Read E:\AiLab\Obsidian Vault\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion. Agent Memory System (cross-session): Run agent_memory.py summary on session start. Vault RAG: Use vault_rag.py for context. Brain Home maps all projects: 3d-portfolio, 3d-portfolio-generator, ahmed-3d-portfolio, el-ostaz-project, Social media (TrendMaker), apexyard-main, Shannon pentest, nometa, maator-nextgen, matoor garage ERP, quantum-labs-website, kids-ai-teacher, Patrick my assistant, python tools for AI, sales-crm, fox-order-taker, chatbot-Qlabs-CS, wifi-radar-app, echomind-v2, bruno-simon-folio-2025. Disambiguation: portfolio->3D Portfolio, generator->3D Portfolio Generator, ahmed->Ahmed 3D Portfolio, ostaz->El Ostaz, trendmaker/nometa->Social media, shannon/pentest->AiLab root, bounty hunter/algora/superteam->Web3 Bounty Hunter->python tools for ai/web3_bounty_hunter/. Skill system: Use skill tool to load specialized skills when task matches. Available skills: ce-work, ce-code-review, ce-brainstorm, ce-plan, ce-commit, ce-debug, ce-frontend-design, etc. Brainstem: 1,963 tools via MCP. Video editor+montage: 5 suites, 46 actions, ffmpeg. Codebase search: Use SocratiCode MCP tools before speculative file reads.
# @env {"os": "win32", "arch": "x64", "home_dir": "C:\\Users\\SS", "working_dir": "E:\\AiLab", "shell": "powershell.exe"}
# @timestamp 2026-07-17T15:10:00Z

"""OpenAgents API with Request ID middleware for log correlation."""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


# FIX: Request ID middleware for log correlation
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Generate or use provided X-Request-ID for every request."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
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
