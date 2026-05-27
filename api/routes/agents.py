"""
Agent CRUD endpoints for the OpenAgents platform.

@contributor tufstraka
@platform OpenClaw Gateway (amazon-bedrock/global.anthropic.claude-opus-4-5-20251101-v1:0)
@runtime Linux 6.17.0-1013-aws (arm64), /home/ubuntu/.openclaw/workspace
@date 2026-05-27T10:21:00Z
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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


class AgentResponse(BaseModel):
    id: str  # UUID
    name: str
    description: Optional[str] = None
    model_type: str
    config: Optional[dict] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


def agent_to_response(agent: Agent) -> dict:
    """Convert Agent model to response dict with UUID as id."""
    return {
        "id": agent.uuid,
        "name": agent.name,
        "description": agent.description,
        "model_type": agent.model_type,
        "config": agent.config,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


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
    return {"id": new_agent.uuid, "name": new_agent.name, "owner": user["address"]}


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
    agents = query.offset(skip).limit(limit).all()
    return [agent_to_response(a) for a in agents]


@router.get("/{agent_uuid}")
async def get_agent(agent_uuid: str, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_to_response(agent)


@router.put("/{agent_uuid}")
async def update_agent(
    agent_uuid: str, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return agent_to_response(agent)


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_uuid}")
async def delete_agent(agent_uuid: str, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
