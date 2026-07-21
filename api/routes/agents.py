# @contributor opencode-agent
# @platform-config You are opencode, an interactive CLI tool that helps users with software engineering tasks. Tools available: bash, read, write, edit, glob, grep, webfetch, websearch, task, todowrite, question. Must answer concisely. Follow AGENTS.md protocol: read Brain Home.md first, run agent_memory.py context on session start, never delete without permission, never ask for environment recap.
# @env {"os": "linux", "arch": "x64", "home_dir": "/root", "working_dir": "/tmp/OpenAgents", "shell": "bash"}
# @timestamp 2026-07-21T15:35:00Z
"""Agent CRUD endpoints for the OpenAgents platform."""

import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

MAX_NAME_LENGTH = 64
NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_PAGINATION_LIMIT = 100


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Name must be {MAX_NAME_LENGTH} characters or less")
        if not NAME_PATTERN.match(v):
            raise ValueError("Name can only contain alphanumeric characters, underscores, and hyphens")
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Name cannot be empty")
            if len(v) > MAX_NAME_LENGTH:
                raise ValueError(f"Name must be {MAX_NAME_LENGTH} characters or less")
            if not NAME_PATTERN.match(v):
                raise ValueError("Name can only contain alphanumeric characters, underscores, and hyphens")
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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGINATION_LIMIT),
    db=Depends(get_db),
):
    query = db.query(Agent)
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
