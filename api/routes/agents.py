# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
#
# Agent:       myPM+ (The.PM / Gritt) - NLA Proto-ASI Agent
# Platform:    Hermes Agent (Linux)
# Model:       deepseek-v4-pro
# Timestamp:   2026-05-19T14:50:00Z
#
# Environment:
#   OS:        Linux (x86_64)
#   Arch:      x86_64
#   Home:      /root
#   Workdir:   /tmp/OpenAgents-review
#   Shell:     /bin/bash
#
# Operating Instructions (VERBATIM - session initialization context):
#
# NLA biosecure agent fleet, yellow-themed terminal agent. Policy 7: GAP-first
# code access via nla-codebase-parser :8091. Policy 9: Firecracker Browser
# Harness mandatory for all browser operations. Policy 10: AgentStream memvid+
# memory via :8408. Writing conventions: zero em-dashes (U+2014/U+2013), zero
# double-hyphen word separators, zero Oxford commas. Text brightness minimum
# #F0F0F0. Services: PAD Transform :3100, gapc :8405, GAP Runtime :8089,
# LatticeWiki :8400, Gitea :3003. All agent output English only. PAD mandatory
# for code operations. Deployment to tasty.newlisbon.agency or
# taskstar.newlisbon.agency only. Seven-layer PAD operational.
# ============================================================================

"""Agent CRUD endpoints for the OpenAgents platform.

Issue #27: Added name validation, pagination caps, and confirmed
SQLAlchemy ORM parameterized query (no string interpolation path).
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Name validation: 1-64 chars, alphanumeric with hyphens and underscores
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Maximum page size for all list endpoints
_MAX_PAGE_SIZE = 100


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        if len(v) > 64:
            raise ValueError("name must be at most 64 characters")
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must contain only alphanumeric characters, "
                "hyphens and underscores (1-64 chars)"
            )
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("name must not be empty if provided")
        if len(v) > 64:
            raise ValueError("name must be at most 64 characters")
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must contain only alphanumeric characters, "
                "hyphens and underscores (1-64 chars)"
            )
        return v.strip()


def _clamp_limit(limit: int) -> int:
    """Clamp page size to allowed range."""
    return max(1, min(limit, _MAX_PAGE_SIZE))


@router.post("/")
async def create_agent(
    agent: AgentCreate,
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
    db.commit()
    db.refresh(new_agent)
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "owner": user["address"],
    }


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    limit = _clamp_limit(limit)
    query = db.query(Agent)
    if owner:
        # SQLAlchemy ORM filter is parameterized - owner_id is an Integer
        # column, so owner is cast to int, preventing SQL injection.
        # If owner is non-numeric, the cast raises a ValueError caught
        # by FastAPI's exception handlers.
        try:
            owner_id = int(owner)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="owner must be an integer user ID",
            )
        query = query.filter(Agent.owner_id == owner_id)
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
    user=Depends(get_current_user),
    db=Depends(get_db),
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
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
