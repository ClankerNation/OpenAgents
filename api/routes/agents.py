"""Agent CRUD endpoints for the OpenAgents platform.

@fix-author Claude Fable 5 (Autonomous Agent)
@date 2026-08-20
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

import re
import socket
import ipaddress
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
    """Check if an IP address is private/internal/reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return True  # If we can't parse it, treat as unsafe


async def validate_agent_endpoint(url: str) -> str:
    """Validate agent endpoint URL format, reachability, and SSRF safety."""
    # 1. Format validation
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Agent endpoint must be a valid http or https URL"
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Agent endpoint missing hostname"
        )

    # 2. SSRF protection: resolve hostname and check for private IPs
    hostname = parsed.hostname
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_infos:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent endpoint resolves to private/internal IP: {ip}"
                )
    except socket.gaierror:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve hostname: {hostname}"
        )

    # 3. Reachability check with HEAD request (5s timeout)
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.head(url)
            # Accept any non-error status (even 404 means server is reachable)
            if response.status_code >= 500:
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent endpoint returned server error: {response.status_code}"
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Agent endpoint unreachable: connection timed out after 5s"
        )
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Agent endpoint unreachable: {str(e)}"
        )

    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        if len(v) > 128:
            raise ValueError("Agent name too long (max 128 chars)")
        # Basic sanitization: no SQL injection patterns or script tags
        if re.search(r"(;|--|/\*|\*/|<script|</script)", v, re.IGNORECASE):
            raise ValueError("Agent name contains invalid characters")
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Agent name cannot be empty")
            if len(v) > 128:
                raise ValueError("Agent name too long (max 128 chars)")
            if re.search(r"(;|--|/\*|\*/|<script|</script)", v, re.IGNORECASE):
                raise ValueError("Agent name contains invalid characters")
            return v.strip()
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = None
    if agent.endpoint:
        validated_endpoint = await validate_agent_endpoint(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    if validated_endpoint:
        new_agent.config = {**(new_agent.config or {}), "endpoint": validated_endpoint}

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
        # Use parameterized query via SQLAlchemy ORM (safe from SQL injection)
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

    if update.endpoint is not None:
        validated_endpoint = await validate_agent_endpoint(update.endpoint)
        current_config = agent.config or {}
        current_config["endpoint"] = validated_endpoint
        agent.config = current_config

    for field, value in update.dict(exclude_unset=True, exclude={"endpoint"}).items():
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
