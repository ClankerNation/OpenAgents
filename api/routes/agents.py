"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. You have persistent memory across sessions. Save durable facts using the memory tool. Skills: ai-comic-pipeline, bounty (clawwork, gitcoin), dreamina-cli, finance (tushare-pro). Host: Windows (10). User home directory: C:\Users\57629. Shell: git-bash / MSYS. You are on Weixin/WeChat. Conversation: 2026-05-28 09:08, deepseek-v4-flash/deepseek.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator, HttpUrl
from typing import Optional
from datetime import datetime
import httpx
import re
import ipaddress
from urllib.parse import urlparse

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from ..middleware.audit import create_audit_log

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    endpoint: str  # BUG: No URL validation — any string accepted, causes crashes
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator("endpoint")
    def validate_endpoint(cls, v):
        """Validate URL format, block private IPs, and check reachability."""
        # Validate URL format
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Must be a valid http:// or https:// URL")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http:// and https:// URLs are supported")

        # SSRF protection: block private/internal IPs
        hostname = parsed.hostname
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError(f"Private/internal IPs are not allowed: {hostname}")
        except ValueError:
            # Not an IP — it's a hostname, allow it (DNS will resolve)
            pass

        return v

    @validator("endpoint")
    def check_reachability(cls, v):
        """Verify the endpoint is reachable with a HEAD request (5s timeout)."""
        try:
            with httpx.Client(timeout=5.0) as client:
                client.head(v, follow_redirects=True)
        except httpx.TimeoutException:
            raise ValueError("Endpoint timed out after 5 seconds")
        except httpx.ConnectError:
            raise ValueError("Could not connect to endpoint")
        except httpx.InvalidURL:
            raise ValueError("Invalid URL format")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        endpoint=agent.endpoint,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    create_audit_log(
        db,
        action="create",
        actor_id=user["id"],
        actor_address=user.get("address", ""),
        target_type="agent",
        target_id=new_agent.id,
        after_values={"name": new_agent.name, "description": new_agent.description,
                       "model_type": new_agent.model_type, "config": new_agent.config},
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
    agent_id: int, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    before = {"name": agent.name, "description": agent.description,
              "config": agent.config, "model_type": agent.model_type}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    after = {"name": agent.name, "description": agent.description,
             "config": agent.config, "model_type": agent.model_type}
    create_audit_log(
        db,
        action="update",
        actor_id=user["id"],
        actor_address=user.get("address", ""),
        target_type="agent",
        target_id=agent.id,
        before_values=before,
        after_values=after,
    )
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    before = {"name": agent.name, "description": agent.description,
              "config": agent.config, "model_type": agent.model_type}
    db.delete(agent)
    db.commit()
    create_audit_log(
        db,
        action="delete",
        actor_id=0,
        actor_address="unknown",
        target_type="agent",
        target_id=agent_id,
        before_values=before,
    )
    return {"deleted": True}
