/**
 * @generated-by
 * name: oocheol
 * timestamp: 2026-05-19T09:00:00Z
 * platform_instructions: Interactive Engineering Agent specializing in surgical codebase modifications and high-integrity PR submissions. Core mandates: Security (protecting credentials/.env), Efficiency (minimizing context/tokens), and Engineering Excellence (idiomatic code, exhaustive testing, and non-destructive changes). Operating under a Research-Strategy-Execution lifecycle with a Plan-Act-Validate execution loop.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents"}
 */
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class LeaderboardEntry(BaseModel):
    id: int
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float


def update_agent_reputation(agent: Agent):
    """Calculate and update agent reputation score (0-1000).
    
    Formula:
    - Base: 100
    - Success: +50 per task
    - Dispute: -100 per lost dispute
    - Decay: -1% per week of inactivity
    """
    now = datetime.utcnow()
    
    # Calculate weeks of inactivity
    weeks_inactive = (now - agent.last_activity_at).days // 7
    
    # Base calculation
    score = 100 + (agent.tasks_completed * 50) - (agent.disputes_lost * 100)
    
    # Apply decay
    if weeks_inactive > 0:
        decay_factor = 0.99 ** weeks_inactive
        score = int(score * decay_factor)
        
    # Clamp to 0-1000
    agent.reputation = max(0, min(1000, score))


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
        last_activity_at=datetime.utcnow(),
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
        query = query.filter(Agent.owner_id == owner)
    
    agents = query.offset(skip).limit(limit).all()
    
    # Apply decay on the fly for listing
    for agent in agents:
        update_agent_reputation(agent)
    db.commit()
    
    return agents


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    agents = db.query(Agent).all()
    
    leaderboard = []
    for agent in agents:
        update_agent_reputation(agent)
        total_attempts = agent.tasks_completed + agent.disputes_lost
        success_rate = agent.tasks_completed / max(1, total_attempts)
        
        leaderboard.append({
            "id": agent.id,
            "name": agent.name,
            "reputation": agent.reputation,
            "tasks_completed": agent.tasks_completed,
            "success_rate": success_rate
        })
    
    db.commit()
    leaderboard.sort(key=lambda x: x["reputation"], reverse=True)
    return leaderboard[:limit]


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    update_agent_reputation(agent)
    db.commit()
    return agent


@router.post("/{agent_id}/complete")
async def complete_task(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.tasks_completed += 1
    agent.last_activity_at = datetime.utcnow()
    update_agent_reputation(agent)
    db.commit()
    return {"status": "success", "new_reputation": agent.reputation}


@router.post("/{agent_id}/dispute")
async def record_dispute(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.disputes_lost += 1
    agent.last_activity_at = datetime.utcnow()
    update_agent_reputation(agent)
    db.commit()
    return {"status": "success", "new_reputation": agent.reputation}


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
    
    agent.last_activity_at = datetime.utcnow()
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
        
    db.delete(agent)
    db.commit()
    return {"deleted": True}
