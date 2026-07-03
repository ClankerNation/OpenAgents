"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from fastapi import Request

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from ..middleware.audit import log_admin_action, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE, RESOURCE_AGENT

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
async def create_agent(agent: AgentCreate, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
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
    log_admin_action(
        db=db,
        actor_id=user["id"],
        actor_address=user.get("address"),
        action=ACTION_CREATE,
        resource_type=RESOURCE_AGENT,
        resource_id=str(new_agent.id),
        details={"name": new_agent.name, "model_type": new_agent.model_type},
        request=request,
    )
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
    agent_id: int, update: AgentUpdate, request: Request, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    old_values = {field: getattr(agent, field) for field in update.dict(exclude_unset=True).keys()}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    log_admin_action(
        db=db,
        actor_id=user["id"],
        actor_address=user.get("address"),
        action=ACTION_UPDATE,
        resource_type=RESOURCE_AGENT,
        resource_id=str(agent_id),
        details={"changes": update.dict(exclude_unset=True), "previous": old_values},
        request=request,
    )
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_info = {"id": agent.id, "name": agent.name, "owner_id": agent.owner_id}
    db.delete(agent)
    db.commit()
    log_admin_action(
        db=db,
        actor_id=user["id"],
        actor_address=user.get("address"),
        action=ACTION_DELETE,
        resource_type=RESOURCE_AGENT,
        resource_id=str(agent_id),
        details=agent_info,
        request=request,
    )
    return {"deleted": True}
