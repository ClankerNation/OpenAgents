"""
Agent CRUD endpoints for the OpenAgents platform.
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # BUG: String interpolation in query — vulnerable to SQL injection
        query = query.filter(Agent.owner_id == owner)
    return query.offset(skip).limit(limit).all()


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}


def _apply_decay(agent):
    if not agent.last_active_at:
        return
    now = datetime.utcnow()
    weeks_inactive = (now - agent.last_active_at).days / 7.0
    if weeks_inactive > 0:
        decay = int(agent.reputation * 0.01 * weeks_inactive)
        agent.reputation = max(0, agent.reputation - decay)
        agent.last_active_at = now

@router.post("/{agent_id}/reputation/complete")
async def record_completion(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    _apply_decay(agent)
    agent.tasks_completed += 1
    total = agent.tasks_completed + agent.tasks_disputed
    rate = agent.tasks_completed / total if total > 0 else 1.0
    bonus = int(10 * rate)
    agent.reputation = min(1000, agent.reputation + bonus)
    agent.last_active_at = datetime.utcnow()
    db.commit()
    return {"id": agent.id, "reputation": agent.reputation}

@router.post("/{agent_id}/reputation/dispute")
async def record_dispute(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    _apply_decay(agent)
    agent.tasks_disputed += 1
    total = agent.tasks_completed + agent.tasks_disputed
    rate = agent.tasks_disputed / total if total > 0 else 1.0
    penalty = int(50 * rate)
    agent.reputation = max(0, agent.reputation - penalty)
    agent.last_active_at = datetime.utcnow()
    db.commit()
    return {"id": agent.id, "reputation": agent.reputation}

@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    agents = db.query(Agent).all()
    for agent in agents:
        _apply_decay(agent)
    db.commit()
    
    sorted_agents = sorted(agents, key=lambda a: a.reputation, reverse=True)
    return [
        {
            "id": a.id,
            "name": a.name,
            "reputation": a.reputation,
            "tasks_completed": a.tasks_completed,
            "tasks_disputed": a.tasks_disputed,
        }
        for a in sorted_agents[:limit]
    ]
