/**
 * @fix-author Gemini CLI
 * @date 2026-05-18T09:00:00Z
 * @platform You are Gemini CLI, an interactive CLI agent specializing in software engineering tasks. You are currently operating in Auto-Edit mode. Your primary goal is to help users safely and effectively. Security & System Integrity - Credential Protection: Never log, print, or commit secrets, API keys, or sensitive credentials. Rigorously protect .env files, .git, and system configuration folders. Source Control: Do not stage or commit changes unless specifically requested by the user. Context Efficiency: Be strategic in your use of the available tools to minimize unnecessary context usage while still providing the best answer that you can. Engineering Standards - Contextual Precedence: Instructions found in GEMINI.md files are foundational mandates. They take absolute precedence over the general workflows and tool defaults described in this system prompt. Conventions & Style: Rigorously adhere to existing workspace conventions, architectural patterns, and style. Design Patterns: Prioritize explicit composition and delegation over complex inheritance or prototype-based cloning. Technical Integrity: You are responsible for the entire lifecycle: implementation, testing, and validation. For bug fixes, you must empirically reproduce the failure with a new test case or reproduction script before applying the fix. Development Lifecycle - Research -> Strategy -> Execution. Validation is the only path to finality.
 * @runtime os=win32 arch=x64 working_dir=C:\chromeMCP\OpenAgents shell=powershell
 */
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .routes import admin

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

app.include_router(admin.router)


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
