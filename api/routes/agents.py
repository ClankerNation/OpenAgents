# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal (SSRF protection)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return True  # If we can't parse it, reject it


def validate_agent_endpoint(url: str) -> str:
    """Validate agent endpoint URL format, reachability, and SSRF safety."""
    # Parse and validate format
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint must use http or https scheme")
    if not parsed.netloc:
        raise ValueError("Endpoint must have a valid hostname")

    # Resolve hostname and check for private IPs
    try:
        host = parsed.hostname
        addrs = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        for family, _, _, _, sockaddr in addrs:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise ValueError(f"Private/internal IP addresses are not allowed: {ip}")
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {host}")

    # HEAD request to verify reachability (5s timeout)
    try:
        resp = httpx.head(url, timeout=5.0, follow_redirects=True)
        if resp.status_code >= 500:
            raise ValueError(f"Endpoint returned server error: {resp.status_code}")
    except httpx.TimeoutException:
        raise ValueError("Endpoint did not respond within 5 seconds")
    except httpx.HTTPError as e:
        raise ValueError(f"Endpoint unreachable: {str(e)}")

    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        if len(v) > 255:
            raise ValueError("Agent name too long (max 255 chars)")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        return validate_agent_endpoint(v)


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Agent name cannot be empty")
            if len(v) > 255:
                raise ValueError("Agent name too long (max 255 chars)")
            return v.strip()
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_agent_endpoint(v)
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
        endpoint=agent.endpoint,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
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
