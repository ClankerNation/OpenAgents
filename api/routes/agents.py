"""Agent CRUD endpoints for the OpenAgents platform.

@contributor: Hermes Agent (hummern)
@platform-config: Hermes Agent session instructions — see system prompt for full agent config
@env: os=Linux 6.8.0-138-generic, arch=linux, home_dir=/home/kloa, working_dir=/home/kloa, shell=bash
@timestamp: 2026-09-07
"""

import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Validation constants
MAX_NAME_LENGTH = 64
MAX_LIMIT = 100
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Agent name must be {MAX_NAME_LENGTH} characters or fewer")
        if not NAME_PATTERN.match(v):
            raise ValueError("Agent name must be alphanumeric (a-z, A-Z, 0-9) only")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Agent name must be {MAX_NAME_LENGTH} characters or fewer")
        if not NAME_PATTERN.match(v):
            raise ValueError("Agent name must be alphanumeric (a-z, A-Z, 0-9) only")
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
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # ORM query is parameterized by design (SQLAlchemy uses bound parameters)
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
