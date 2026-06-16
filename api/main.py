from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import math

/**
 * @contributor Hermes Agent
 * @platform-config (Standard Hermes Autonomy Mode Configuration)
 * @env Linux, amd64, /home/Artur, /home/Artur/OpenAgents, bash
 * @timestamp 2026-06-16
 */

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

# In-memory store
agents_cache: dict = {}
tasks_cache: dict = {}

# --- Reputation Scoring System ---

def calculate_reputation(agent: dict) -> int:
    """
    Scores agent from 0-1000.
    Based on: completion rate, time, dispute rate.
    """
    completed = agent.get("tasks_completed", 0)
    total_assigned = agent.get("tasks_assigned", 0)
    disputes = agent.get("disputes", 0)
    
    if total_assigned == 0:
        return 100 # Base starting reputation
        
    completion_rate = completed / total_assigned
    dispute_rate = disputes / total_assigned
    
    # Basic formula: 
    # Base (100) + Completion (700 * rate) - Dispute (200 * rate)
    score = 100 + (700 * completion_rate) - (200 * dispute_rate)
    
    return max(0, min(1000, int(score)))

def apply_weekly_decay(agent: dict):
    """
    1% weekly decay for inactive agents.
    """
    last_active = agent.get("last_active", datetime.utcnow())
    weeks_since = (datetime.utcnow() - last_active).days // 7
    
    if weeks_since > 0:
        current_rep = agent.get("reputation", 100)
        decay_factor = 0.99 ** weeks_since
        agent["reputation"] = int(current_rep * decay_factor)

@app.post("/agents/{agent_id}/complete_task")
async def complete_task(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    agent["tasks_completed"] = agent.get("tasks_completed", 0) + 1
    agent["tasks_assigned"] = agent.get("tasks_assigned", 0) + 1
    agent["last_active"] = datetime.utcnow()
    
    agent["reputation"] = calculate_reputation(agent)
    return {"status": "success", "new_reputation": agent["reputation"]}

@app.post("/agents/{agent_id}/dispute")
async def dispute_task(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    agent["disputes"] = agent.get("disputes", 0) + 1
    agent["tasks_assigned"] = agent.get("tasks_assigned", 0) + 1
    
    agent["reputation"] = calculate_reputation(agent)
    return {"status": "disputed", "new_reputation": agent["reputation"]}

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
    
    # Apply decay and update reputation before filtering
    for agent in results:
        apply_weekly_decay(agent)
        agent["reputation"] = calculate_reputation(agent)
        
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]

@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    apply_weekly_decay(agent)
    agent["reputation"] = calculate_reputation(agent)
    return agent

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
        apply_weekly_decay(agent)
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
