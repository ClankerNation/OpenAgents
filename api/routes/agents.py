"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from .admin import record_audit

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


@router.post("/")
async def create_agent(
    agent: AgentCreate,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.flush()

    record_audit(
        db,
        action="agent.create",
        actor_id=str(user["id"]),
        target_type="agent",
        target_id=str(new_agent.id),
        after_value={"name": agent.name, "model_type": agent.model_type},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
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
    agent_id: int,
    update: AgentUpdate,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")

    before = {"name": agent.name, "description": agent.description, "config": agent.config}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    after = {"name": agent.name, "description": agent.description, "config": agent.config}

    record_audit(
        db,
        action="agent.update",
        actor_id=str(user["id"]),
        target_type="agent",
        target_id=str(agent_id),
        before_value=before,
        after_value=after,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")

    record_audit(
        db,
        action="agent.delete",
        actor_id=str(user["id"]),
        target_type="agent",
        target_id=str(agent_id),
        before_value={"name": agent.name, "owner_id": agent.owner_id},
        ip_address=request.client.host if request.client else None,
    )
    db.delete(agent)
    db.commit()
    return {"deleted": True}
