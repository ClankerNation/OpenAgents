"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import socket
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Allow only public, non-loopback, non-private IP ranges
_PRIVATE_IPS = re.compile(
    r"^https?://(127\.\d{1,3}\.\d{1,3}\.\d{1,3}"  # loopback
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"              # 10/8
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"   # 172.16-31/12
    r"|192\.168\.\d{1,3}\.\d{1,3}"                  # 192.168/16
    r"|169\.254\.\d{1,3}\.\d{1,3}"                  # link-local
    r"|::1"                                         # IPv6 loopback
    r"|fe80:"                                       # IPv6 link-local
    r"|127\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"    # IPv4-mapped
    r")(:\d+)?$"
)

# Strict URL regex: scheme://host[:port]/path
_URL_RE = re.compile(
    r"^https?://"
    r"[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?"  # host
    r"(\.[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?)*"  # subdomains
    r"(:\d{1,5})?"                                # optional port
    r"(/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%{}]*)?$"  # optional path
)


class AgentCreate(BaseModel):
    """Schema for registering a new agent."""

    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str  # HTTP(S) URL where the agent listens for tasks

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name must not be empty")
        if len(v) > 128:
            raise ValueError("Agent name must be <= 128 characters")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate URL format, scheme, and SSRF protection."""
        if not _URL_RE.match(v):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        if _PRIVATE_IPS.match(v):
            raise ValueError("Endpoint must not resolve to a private or loopback IP")
        return v.lower()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


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
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"], "endpoint": new_agent.endpoint}


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
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
