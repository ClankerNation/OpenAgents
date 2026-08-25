# @fix-author rafaio1
# @date 2026-08-25T07:10:00Z
# @runtime linux x64 /tmp/openagents_issue_187 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for agent endpoint URL validation (Issue #187)
"""Agent CRUD endpoints for the OpenAgents platform.

Implements strict input validation, SSRF protection via private IP blocking,
and reachability verification for agent endpoint URLs per Issue #187.
Closes #187
"""
import ipaddress
import re
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..middleware.auth import get_current_user
from ..models.database import Agent, get_db

router = APIRouter(prefix="/agents", tags=["agents"])

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 _\-\.]{1,128}$")


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return False


async def validate_endpoint_url(url: str) -> str:
    """Validate agent endpoint URL format, block SSRF, and verify reachability."""
    parsed = urlparse(url)

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint URL must use http or https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Endpoint URL must have a valid hostname")

    # Resolve hostname and check for private IPs (SSRF protection)
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                raise ValueError(
                    f"Endpoint URL resolves to private/reserved IP ({ip_str}) — blocked for SSRF protection"
                )
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    # Verify reachability with HEAD request (5s timeout)
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.head(url)
            # Accept any non-error status (2xx, 3xx, even 4xx means server is reachable)
            if response.status_code >= 500:
                raise ValueError(f"Endpoint returned server error ({response.status_code})")
    except httpx.TimeoutException:
        raise ValueError(f"Endpoint URL timed out after 5 seconds: {url}")
    except httpx.ConnectError:
        raise ValueError(f"Cannot connect to endpoint URL: {url}")
    except Exception as e:
        raise ValueError(f"Endpoint URL unreachable: {str(e)}")

    return url


class AgentCreate(BaseModel):
    """Validated payload for agent creation."""
    name: str = Field(..., min_length=1, max_length=128)
    endpoint: str = Field(..., description="HTTP/HTTPS URL where the agent can be reached")
    description: Optional[str] = Field(None, max_length=1024)
    model_type: str = Field(default="gpt-4", pattern=r"^[a-zA-Z0-9\-_]{1,64}$")
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must be 1-128 chars, alphanumeric/spaces/hyphens/underscores/dots only"
            )
        return v

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = re.sub(r"<[^>]+>", "", v).strip()
        if len(cleaned) > 1024:
            raise ValueError("description exceeds 1024 characters after sanitization")
        return cleaned


class AgentUpdate(BaseModel):
    """Validated payload for agent updates — all fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    endpoint: Optional[str] = None
    description: Optional[str] = Field(None, max_length=1024)
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must be 1-128 chars, alphanumeric/spaces/hyphens/underscores/dots only"
            )
        return v

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
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Validate endpoint URL format, SSRF, and reachability
    try:
        validated_endpoint = await validate_endpoint_url(agent.endpoint)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    # Store validated endpoint
    new_agent.endpoint = validated_endpoint

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

    # If endpoint is being updated, validate it
    if update.endpoint is not None:
        try:
            validated_endpoint = await validate_endpoint_url(update.endpoint)
            agent.endpoint = validated_endpoint
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    for field, value in update.model_dump(exclude_unset=True, exclude={"endpoint"}).items():
        setattr(agent, field, value)

    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int = Query(..., ge=1),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete an agent — requires authentication and ownership check."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
