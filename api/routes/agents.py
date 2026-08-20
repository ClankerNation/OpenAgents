"""
@contributor-info rafaio1
@timestamp 2026-08-20T08:45:00Z
@env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None


def _validate_agent_endpoint(url: str) -> str:
    """Validate agent endpoint URL format, reachability, and SSRF safety."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Endpoint must use http or https scheme")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Endpoint missing hostname")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Endpoint missing hostname")

    # Resolve and block private/internal IPs (SSRF protection)
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Cannot resolve hostname: {hostname}")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(
                    status_code=400,
                    detail=f"Private/internal IP addresses are not allowed: {ip_str}",
                )
        except ValueError:
            continue

    # HEAD request to verify reachability (5s timeout)
    try:
        resp = httpx.head(url, timeout=5.0, follow_redirects=True)
        if resp.status_code >= 500:
            raise HTTPException(
                status_code=400,
                detail=f"Endpoint returned server error (HTTP {resp.status_code})",
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Endpoint unreachable: request timed out after 5s")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Endpoint unreachable: {str(e)}")

    return url


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = None
    if agent.endpoint is not None:
        validated_endpoint = _validate_agent_endpoint(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint=validated_endpoint,
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
