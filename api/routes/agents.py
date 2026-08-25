# @fix-author rafaio1
# @date 2026-08-25T04:15:00Z
# @runtime linux x64 /tmp/openagents_issue_173 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for endpoint URL validation (Issue #173)
"""Agent CRUD endpoints for the OpenAgents platform.

Implements strict input validation, parameterized queries, and authentication
enforcement on all mutation endpoints per Issue #173 requirements.

Closes #173
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..middleware.auth import get_current_user
from ..models.database import Agent, get_db

router = APIRouter(prefix="/agents", tags=["agents"])

# Object Calisthenics: Wrap primitive string in a validated value object
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 _\-\.]{1,128}$")


class AgentName(str):
    """Value object enforcing agent name constraints at the type level."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: str) -> str:
        if not isinstance(v, str):
            raise TypeError("string required")
        v = v.strip()
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must be 1-128 chars, alphanumeric/spaces/hyphens/underscores/dots only"
            )
        return v


class AgentCreate(BaseModel):
    """Validated payload for agent creation."""

    name: AgentName
    description: Optional[str] = Field(None, max_length=1024)
    model_type: str = Field(default="gpt-4", pattern=r"^[a-zA-Z0-9\-_]{1,64}$")
    config: Optional[dict] = None

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Strip HTML tags to prevent stored XSS
        cleaned = re.sub(r"<[^>]+>", "", v).strip()
        if len(cleaned) > 1024:
            raise ValueError("description exceeds 1024 characters after sanitization")
        return cleaned


class AgentUpdate(BaseModel):
    """Validated payload for agent updates — all fields optional."""

    name: Optional[AgentName] = None
    description: Optional[str] = Field(None, max_length=1024)
    config: Optional[dict] = None

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = re.sub(r"<[^>]+>", "", v).strip()
        if len(cleaned) > 1024:
            raise ValueError("description exceeds 1024 characters after sanitization")
        return cleaned


@router.post("/")
async def create_agent(
    agent: AgentCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    new_agent = Agent(
        name=str(agent.name),
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
    owner: Optional[str] = Query(None, max_length=128, pattern=r"^[a-zA-Z0-9\-_]+$"),
    skip: int = Query(0, ge=0, le=10000),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner is not None:
        # Parameterized query via SQLAlchemy ORM — no string interpolation
        query = query.filter(Agent.owner_id == owner)
    return query.offset(skip).limit(limit).all()


@router.get("/{agent_id}")
async def get_agent(agent_id: int = Query(..., ge=1), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int = Query(..., ge=1),
    update: AgentUpdate = ...,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int = Query(..., ge=1),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete an agent — now requires authentication and ownership check."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
