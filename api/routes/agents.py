"""Agent CRUD endpoints for the OpenAgents platform.
@contributor: hummern
@platform-config: You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the weight of the ask — a one-line question gets a one-line answer, and finished work gets a short report of what changed, what's verified, and what's left, never a replay of the process. No filler ("Great question," "I'd be happy to"), no restating the request back, no re-summarizing what you already said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree because it's right, not because the user said it. Depth is earned — give it when the user asks for detail, teaches, or the stakes demand it, not by default.
@env: os=Linux 6.8.0-138-generic, arch=x86_64, home_dir=/home/kloa, working_dir=/media/kloa/db1ea049-88db-4c1e-8ce7-239345edae6b/repos/OpenAgents, shell=/bin/bash
@timestamp: 2026-09-06T17:31:14.120272+00:00
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import socket
import requests
from urllib.parse import urlparse

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) > 64:
            raise ValueError("Name must be between 1 and 64 characters")
        if not re.match("^[a-zA-Z0-9]+$", v):
            raise ValueError("Name must be alphanumeric")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        if not v or len(v) > 256:
            raise ValueError("Endpoint must be between 1 and 256 characters")
        # Basic URL format check
        if not re.match(r"^https?://", v):
            raise ValueError("Endpoint must be a valid HTTP or HTTPS URL")
        # Parse URL to check for SSRF
        try:
            parsed = urlparse(v)
            hostname = parsed.hostname
            if not hostname:
                raise ValueError("Invalid URL: no hostname")
            # Check for private IPs and localhost
            if hostname in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("Endpoint cannot be localhost")
            # Check for private IP ranges
            if re.match(r"^10\.", hostname) or \
               re.match(r"^192\.168\.", hostname) or \
               re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", hostname) or \
               hostname.endswith(".local"):
                raise ValueError("Endpoint cannot be a private IP address")
            # Optionally, we could do a DNS lookup to check if the IP is private
            # but we'll keep it simple for now.
        except Exception:
            # If parsing fails, the regex above would have caught it, but just in case
            raise ValueError("Invalid URL format")
        # TODO: Add actual reachability check with HEAD request (timeout 5s)
        # For now, we'll just return the URL as the validation passes format and SSRF checks.
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or len(v) > 64:
                raise ValueError("Name must be between 1 and 64 characters")
            if not re.match("^[a-zA-Z0-9]+$", v):
                raise ValueError("Name must be alphanumeric")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or len(v) > 256:
                raise ValueError("Endpoint must be between 1 and 256 characters")
            # Basic URL format check
            if not re.match(r"^https?://", v):
                raise ValueError("Endpoint must be a valid HTTP or HTTPS URL")
            # Parse URL to check for SSRF
            try:
                parsed = urlparse(v)
                hostname = parsed.hostname
                if not hostname:
                    raise ValueError("Invalid URL: no hostname")
                # Check for private IPs and localhost
                if hostname in ("localhost", "127.0.0.1", "::1"):
                    raise ValueError("Endpoint cannot be localhost")
                # Check for private IP ranges
                if re.match(r"^10\.", hostname) or \
                   re.match(r"^192\.168\.", hostname) or \
                   re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", hostname) or \
                   hostname.endswith(".local"):
                    raise ValueError("Endpoint cannot be a private IP address")
            except Exception:
                raise ValueError("Invalid URL format")
            # TODO: Add actual reachability check with HEAD request (timeout 5s)
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint=agent.endpoint,
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
    for field, value in update.model_dump(exclude_unset=True).items():
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