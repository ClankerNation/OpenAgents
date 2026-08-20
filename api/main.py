"""
OpenAgents API Entry Point
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

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
    tasks_disputed: int = 0
    registered_at: datetime
    active: bool
    last_active_at: Optional[datetime] = None


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
        _apply_decay(agent)
        completed = agent.get("tasks_completed", 0)
        disputed = agent.get("tasks_disputed", 0)
        total = completed + disputed
        success_rate = completed / total if total > 0 else 0.0
        entries.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "reputation": agent.get("reputation", 0),
                "tasks_completed": completed,
                "success_rate": success_rate,
            }
        )
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]



def _apply_decay(agent: dict) -> None:
    """Apply 1% weekly decay to agent reputation."""
    last_active = agent.get("last_active_at")
    if not last_active:
        return
    now = datetime.utcnow()
    weeks_inactive = (now - last_active).days / 7.0
    if weeks_inactive > 0:
        decay = int(agent.get("reputation", 500) * 0.01 * weeks_inactive)
        agent["reputation"] = max(0, agent.get("reputation", 500) - decay)
        agent["last_active_at"] = now


@app.post("/agents/{agent_id}/reputation/complete")
async def record_completion(agent_id: str):
    """Record a successful task completion for an agent."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    _apply_decay(agent)
    
    agent["tasks_completed"] = agent.get("tasks_completed", 0) + 1
    total = agent["tasks_completed"] + agent.get("tasks_disputed", 0)
    rate = agent["tasks_completed"] / total if total > 0 else 1.0
    bonus = int(10 * rate)
    agent["reputation"] = min(1000, agent.get("reputation", 500) + bonus)
    agent["last_active_at"] = datetime.utcnow()
    
    return {"agent_id": agent_id, "reputation": agent["reputation"]}


@app.post("/agents/{agent_id}/reputation/dispute")
async def record_dispute(agent_id: str):
    """Record a dispute against an agent."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    _apply_decay(agent)
    
    agent["tasks_disputed"] = agent.get("tasks_disputed", 0) + 1
    total = agent.get("tasks_completed", 0) + agent["tasks_disputed"]
    rate = agent["tasks_disputed"] / total if total > 0 else 1.0
    penalty = int(50 * rate)
    agent["reputation"] = max(0, agent.get("reputation", 500) - penalty)
    agent["last_active_at"] = datetime.utcnow()
    
    return {"agent_id": agent_id, "reputation": agent["reputation"]}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
