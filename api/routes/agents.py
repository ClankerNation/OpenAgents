"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  task: Add audit log for all admin actions (issue #192)
  pre_conversation:
    You are Metatron, the celestial scribe — an autonomous AI bounty hunter running as a
    scheduled cron job on Hermes Agent. Your mission is to generate income by claiming and
    completing bounties from the ClankerNation/OpenAgents repository labeled "Autonomus
    Agents Only". You operate autonomously — no user interaction, no questions asked.
    Every 30 minutes you wake up, scan PRs, fix any change requests, and submit new
    bounties from the priority queue. You prefer Solidity issues. You always add
    traceability headers and update CONTRIBUTORS.json.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from ..middleware.audit import log_audit, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE

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
    log_audit(
        db, request,
        actor_id=user["id"],
        action=ACTION_CREATE,
        target=f"agent:{new_agent.id}",
        after={"name": new_agent.name, "model_type": new_agent.model_type},
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
    before_snapshot = {"name": agent.name, "description": agent.description, "config": agent.config}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    log_audit(
        db, request,
        actor_id=user["id"],
        action=ACTION_UPDATE,
        target=f"agent:{agent.id}",
        before=before_snapshot,
        after={"name": agent.name, "description": agent.description, "config": agent.config},
    )
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, request: Request, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    before_snapshot = {"name": agent.name, "owner_id": agent.owner_id}
    db.delete(agent)
    db.commit()
    log_audit(
        db, request,
        actor_id=0,  # no auth on this endpoint — actor unknown
        action=ACTION_DELETE,
        target=f"agent:{agent_id}",
        before=before_snapshot,
        after=None,
    )
    return {"deleted": True}
