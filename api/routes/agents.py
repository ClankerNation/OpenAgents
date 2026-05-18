"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent, ReputationEvent
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

@router.post("/{agent_id}/reputation/completion")
async def agent_reputation_completion(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    event = ReputationEvent(agent_id=agent_id, event_type="completion", score_delta=10)
    agent.reputation = min(agent.reputation + 10, 1000)
    agent.tasks_completed += 1
    agent.last_active_at = datetime.utcnow()
    db.add(event)
    db.commit()
    db.refresh(agent)
    return agent

@router.post("/{agent_id}/reputation/dispute")
async def agent_reputation_dispute(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    event = ReputationEvent(agent_id=agent_id, event_type="dispute", score_delta=-20)
    agent.reputation = max(agent.reputation - 20, 0)
    agent.disputes += 1
    agent.last_active_at = datetime.utcnow()
    db.add(event)
    db.commit()
    db.refresh(agent)
    return agent

@router.post("/reputation/decay")
async def agent_reputation_decay(db=Depends(get_db)):
    from datetime import timedelta
    threshold = datetime.utcnow() - timedelta(days=7)
    agents = db.query(Agent).filter(Agent.last_active_at < threshold).all()
    
    for agent in agents:
        decay_amount = max(1, int(agent.reputation * 0.01))
        if decay_amount > 0 and agent.reputation > 0:
            agent.reputation = max(agent.reputation - decay_amount, 0)
            event = ReputationEvent(agent_id=agent.id, event_type="decay", score_delta=-decay_amount)
            db.add(event)
            
    db.commit()
    return {"processed": len(agents)}

@router.get("/leaderboard/top")
async def leaderboard(limit: int = Query(20, le=50), db=Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.reputation.desc()).limit(limit).all()
    entries = []
    for agent in agents:
        completed = agent.tasks_completed
        disputes = agent.disputes
        total = completed + disputes
        success_rate = completed / max(total, 1)
        entries.append({
            "agent_id": str(agent.id),
            "name": agent.name,
            "reputation": agent.reputation,
            "tasks_completed": completed,
            "success_rate": success_rate
        })
    return entries

# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
