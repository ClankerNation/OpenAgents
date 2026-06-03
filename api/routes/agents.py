"""
@contributor-info
  agent: Kelthos-X Hermes Agent
  session_id: clanker-bounty-fix-173
  timestamp: 2026-06-03T07:00:00Z
  os: Linux 6.8.0-106-generic
  arch: x86_64
  home_dir: /root
  working_dir: /root/HUNT/clanker-bounty
  shell: /usr/bin/bash
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import ipaddress
import socket
import httpx
from urllib.parse import urlparse

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Private/internal IP ranges to block (SSRF protection)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_endpoint_url(url: str) -> str:
    """Validate an agent endpoint URL — must be valid http/https, reachable, not private."""
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")

    # Must have a hostname
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")

    # Block private/internal IPs (SSRF protection)
    try:
        addr = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        # Hostname — resolve and check all IPs
        try:
            addr_info = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")

        for info in addr_info:
            ip = ipaddress.ip_address(info[4][0])
            for network in BLOCKED_NETWORKS:
                if ip in network:
                    raise ValueError(
                        f"Hostname {parsed.hostname} resolves to private/internal IP {ip} — blocked"
                    )
    else:
        # Direct IP — check if blocked
        for network in BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(f"Private/internal IP not allowed: {addr}")

    return parsed.geturl()


async def check_endpoint_reachable(url: str, timeout: float = 5.0) -> bool:
    """Verify the endpoint responds to a HEAD request."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.head(url, follow_redirects=True)
            return resp.status_code < 500
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError):
        return False


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint: str  # Agent's callback URL — validated for format, reachability, and SSRF
    config: Optional[dict] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid(cls, v: str) -> str:
        return validate_endpoint_url(v)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Agent name cannot be empty")
        if len(stripped) > 128:
            raise ValueError("Agent name must be 128 characters or fewer")
        return stripped


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_if_provided_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_endpoint_url(v)
        return v

    @field_validator("name")
    @classmethod
    def name_if_provided_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Agent name cannot be empty")
            if len(stripped) > 128:
                raise ValueError("Agent name must be 128 characters or fewer")
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Verify endpoint is reachable before creating agent
    reachable = await check_endpoint_reachable(agent.endpoint, timeout=5.0)
    if not reachable:
        raise HTTPException(
            status_code=400,
            detail=f"Agent endpoint {agent.endpoint} is not reachable. Ensure the URL is correct and the agent is running.",
        )

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        endpoint=agent.endpoint,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "endpoint": new_agent.endpoint,
        "owner": user["address"],
    }


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

    update_data = update.dict(exclude_unset=True)

    # If endpoint changed, validate and verify reachability
    if "endpoint" in update_data:
        reachable = await check_endpoint_reachable(update_data["endpoint"], timeout=5.0)
        if not reachable:
            raise HTTPException(
                status_code=400,
                detail=f"New endpoint {update_data['endpoint']} is not reachable.",
            )

    for field, value in update_data.items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
