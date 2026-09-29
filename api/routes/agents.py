"""
@contributor doubao-agent (spiritwanghs fork)
@platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
@env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
@timestamp 2026-09-29T03:40:00Z
"""
"""Agent CRUD endpoints for the OpenAgents platform."""

import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Name: 1-64 chars, alphanumeric (underscore/hyphen allowed, no quotes or markup).
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not _NAME_RE.match(v):
            raise ValueError("name must be 1-64 alphanumeric characters (_, - allowed)")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None and not _NAME_RE.match(v):
            raise ValueError("name must be 1-64 alphanumeric characters (_, - allowed)")
        return v


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
    limit: int = Query(50, ge=1, le=100),  # pagination capped at 100
    db=Depends(get_db),
):
    # Parameterized filtering only — no string interpolation.
    query = db.query(Agent)
    if owner:
        if not re.match(r"^0x[0-9a-fA-F]{40}$", owner):
            raise HTTPException(status_code=400, detail="Invalid owner address format")
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


# Auth required to delete — and only the owner may delete their own agent.
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the owner can delete")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
