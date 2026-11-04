# @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
# @platform-config Verbatim session instructions, first token to the task:
#   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
#   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
#   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
#   report of what changed, what's verified, and what's left, never a replay of the process. No
#   filler, no restating the request back, no re-summarizing what you already said, no narrating
#   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
#   because it's right, not because the user said it. Depth is earned."
#   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
#   a working artifact backed by real tool output — not a description of one. Do not stop after
#   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
#   code or produced the requested result."
#   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
#   or plan to do without actually doing it."
#   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
#   'done' means every named acceptance criterion is verified — never a plausible subset."
#   "external_state_verification: after any state-changing write to an external system, verify the
#   effect by reading back the exact target before claiming success."
#   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
#   read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
#   web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
# @env os=windows arch=x86_64 home_dir=C:\Users\2
#   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
# @timestamp 2026-11-04T14:05:00Z
# ---------------------------------------------------------------

from fastapi import FastAPI, HTTPException, Query

from .routes import agents as agent_routes, payments as payment_routes, tasks as task_routes
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

app.include_router(agent_routes.router)
app.include_router(task_routes.router)
app.include_router(payment_routes.router)


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
