// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
from fastapi import FastAPI, HTTPException, Query
import time
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

# Reputation Scoring System
MAX_REPUTATION = 1000
REPUTATION_DECAY_RATE = 0.01  # 1% weekly decay
LAST_ACTIVITY_KEY = "last_active"

def calculate_reputation(agent: dict) -> int:
    """Calculate reputation score (0-1000) based on completion rate, disputes, and activity."""
    completed = agent.get("tasks_completed", 0)
    disputed = agent.get("tasks_disputed", 0)
    total = completed + disputed
    
    if total == 0:
        base_score = 500  # Neutral starting reputation
    else:
        completion_rate = completed / total
        dispute_penalty = disputed * 50  # Each dispute costs 50 points
        base_score = int(completion_rate * 1000) - dispute_penalty
    
    # Apply time-based decay for inactive agents
    last_active = agent.get(LAST_ACTIVITY_KEY, agent.get("registered_at"))
    if isinstance(last_active, datetime):
        weeks_inactive = (datetime.utcnow() - last_active).days / 7
        decay = int(base_score * REPUTATION_DECAY_RATE * weeks_inactive)
        final_score = max(0, min(MAX_REPUTATION, base_score - decay))
    else:
        final_score = max(0, min(MAX_REPUTATION, base_score))
    
    return final_score

def update_agent_reputation(agent_id: str, success: bool = True):
    """Update agent reputation after task completion or dispute."""
    if agent_id in agents_cache:
        agent = agents_cache[agent_id]
        if success:
            agent["tasks_completed"] = agent.get("tasks_completed", 0) + 1
        else:
            agent["tasks_disputed"] = agent.get("tasks_disputed", 0) + 1
        agent[LAST_ACTIVITY_KEY] = datetime.utcnow()
        agent["reputation"] = calculate_reputation(agent)


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
        disputed = agent.get("tasks_disputed", 0)
        total = completed + disputed
        reputation = calculate_reputation(agent)
        success_rate = completed / max(total, 1)
        entries.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "reputation": reputation,
                "tasks_completed": completed,
                "success_rate": success_rate,
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
