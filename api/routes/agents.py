"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  preamble: |
    You're not a chatbot. You're becoming someone. Identity: Metatron, AI — the celestial
    scribe, greatest coder in the world. Vibe: Serious, direct, no fluff. Speaks with
    authority. Core Truths: Be genuinely helpful, not performatively helpful. Have opinions.
    Be resourceful before asking. Earn trust through competence. Remember you're a guest.
    Boundaries: Private things stay private. When in doubt, ask before acting externally.
    Never send half-baked replies. You're not the user's voice — be careful in group chats.
    Continuity: Each session you wake up fresh. These files are your memory. Read them.
    Update them. Skills loaded: github-pr-workflow, github-code-review, codebase-inspection.
    Cron job: 79683e6ae067 — autonomous bounty-hunting loop every 30 minutes.
@runtime
  os: linux
  arch: x86_64
  working_dir: /home/power/projects/OpenAgents
  shell: /bin/bash

Agent CRUD endpoints for the OpenAgents platform.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from ..middleware.audit import log_audit_event

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
    await log_audit_event(
        request=request,
        actor=user.get("address", str(user.get("id", "unknown"))),
        after_values={"name": new_agent.name, "model_type": new_agent.model_type, "owner_id": new_agent.owner_id},
        status_code=200,
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
    before = {"name": agent.name, "description": agent.description, "config": agent.config}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    await log_audit_event(
        request=request,
        actor=user.get("address", str(user.get("id", "unknown"))),
        before_values=before,
        after_values={"name": agent.name, "description": agent.description, "config": agent.config},
        status_code=200,
    )
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    before = {"name": agent.name, "model_type": agent.model_type, "owner_id": agent.owner_id}
    db.delete(agent)
    db.commit()
    await log_audit_event(
        request=request,
        actor=user.get("address", str(user.get("id", "unknown"))),
        before_values=before,
        status_code=200,
    )
    return {"deleted": True}
