"""Agent CRUD endpoints for the OpenAgents platform.

CONTRIBUTOR TRACEABILITY HEADER
Agent: Atlas (Sovereign Bounty Fleet)
Platform Instructions: [ Bounty $9k ] [ API ] Fix agents.py doesn't validate endpoint URL for
Session Start: 2026-10-03T23:30:00Z
Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-9810596dadd1
Platform: GitHub (ClankerNation/OpenAgents)
Issue: #173 — [ Bounty $9k ] [ API ] Fix agents.py doesn't validate endpoint URL for
"""

import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 64

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v) > NAME_MAX_LENGTH:
            raise ValueError(f"Name must be {NAME_MAX_LENGTH} characters or fewer")
        if not NAME_PATTERN.match(v):
            raise ValueError("Name must contain only alphanumeric characters, underscores, hyphens, or periods")
        return v.strip()

    @field_validator("model_type")
    @classmethod
    def validate_model_type(cls, v: str) -> str:
        allowed = ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo", "claude-3", "claude-3-haiku"]
        if v not in allowed:
            raise ValueError(f"model_type must be one of: {', '.join(allowed)}")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Name cannot be empty")
            if len(v) > NAME_MAX_LENGTH:
                raise ValueError(f"Name must be {NAME_MAX_LENGTH} characters or fewer")
            if not NAME_PATTERN.match(v):
                raise ValueError("Name must contain only alphanumeric characters, underscores, hyphens, or periods")
            return v.strip()
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
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # FIX: Validate owner is a valid integer ID before querying
        try:
            owner_id = int(owner)
            query = query.filter(Agent.owner_id == owner_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid owner ID format")
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
