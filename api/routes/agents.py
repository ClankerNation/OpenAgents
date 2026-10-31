"""
Contributor Metadata (required for bounty #187)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import ipaddress
import socket
import urllib.parse
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/internal IP (SSRF protection)."""
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        # Hostname, not IP — resolve it
        try:
            resolved = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved)
            return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
        except (socket.gaierror, ValueError):
            return False


def _validate_url(url: str) -> str:
    """Validate URL format and SSRF protection."""
    if not url:
        raise ValueError("URL cannot be empty")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must use http or https scheme")

    if not parsed.netloc:
        raise ValueError("URL must have a valid host")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname")

    if _is_private_ip(hostname):
        raise ValueError("Private/internal IP addresses are not allowed")

    return url


async def _check_reachability(url: str, timeout: float = 5.0) -> bool:
    """Check if URL is reachable via HEAD request."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.head(url, follow_redirects=True)
            return response.status_code < 500
    except (httpx.TimeoutException, httpx.RequestError):
        return False


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v) > 100:
            raise ValueError("Name must be 100 characters or less")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_url(v)


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_url(v)


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Validate endpoint reachability if provided
    if agent.endpoint:
        reachable = await _check_reachability(agent.endpoint)
        if not reachable:
            raise HTTPException(
                status_code=422,
                detail=f"Endpoint URL is not reachable: {agent.endpoint}",
            )

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        endpoint=agent.endpoint,
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

    # Validate endpoint reachability if updating
    if update.endpoint:
        reachable = await _check_reachability(update.endpoint)
        if not reachable:
            raise HTTPException(
                status_code=422,
                detail=f"Endpoint URL is not reachable: {update.endpoint}",
            )

    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


# BUG: No authentication � anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
