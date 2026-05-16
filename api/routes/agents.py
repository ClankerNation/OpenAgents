# @fix-author: Hermes Agent (阿铭)
# @date: 2026-05-17
# @platform_instructions: Subagent task — Implement bounty #187 for OpenAgents: add URL validation with SSRF protection to agent registration endpoint. Requirements: validate http/https scheme, HEAD request reachability check with 5s timeout, reject 10.x/192.168.x/172.16-31.x/127.x/169.254.x/0.0.0.0/fc00::/7/::1 private IPs, store validated URL, add pytest tests, create PR against upstream ClankerNation/OpenAgents main. Git token at /tmp/gh_token.txt. Repo at /tmp/OpenAgents (hamademon168-bot fork).
# @runtime: os=Linux (WSL2), arch=x86_64, home_dir=/home/hamademon, working_dir=/mnt/c/Users/26713, shell=/bin/bash

"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator, ValidationError
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# SSRF-protected private/internal IP ranges
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]


def _is_private_host(hostname: str) -> bool:
    """Check whether a hostname resolves to a private/internal IP address.

    Resolves both IPv4 and IPv6 addresses and checks each against the
    blocked network ranges.  Treats resolution failures as private to
    fail closed.
    """
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Cannot resolve — fail closed (treat as private)
        return True

    resolved_ips = set()
    for family, _, _, _, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        # Strip scope ID from IPv6 addresses (e.g. fe80::1%eth0)
        if "%" in ip_str:
            ip_str = ip_str.split("%", 1)[0]
        resolved_ips.add(ip_str)

    for ip_str in resolved_ips:
        try:
            ip_addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        for net in _PRIVATE_NETWORKS:
            if ip_addr in net:
                return True

    return False


def _validate_endpoint_url(url: str) -> str:
    """Validate an agent endpoint URL with SSRF protection.

    Returns the normalized URL string on success.  Raises ValueError
    with a user-facing message on failure.
    """
    # 1. Basic URL structure check
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint URL must use http or https scheme")
    if not parsed.hostname:
        raise ValueError("Endpoint URL must include a hostname")

    # 2. SSRF: reject private / internal IPs
    if _is_private_host(parsed.hostname):
        raise ValueError("Endpoint URL must not resolve to a private or internal IP address")

    # 3. Reachability check (HEAD request, 5 s timeout)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.head(url, follow_redirects=True)
    except httpx.TimeoutException:
        raise ValueError("Endpoint URL is unreachable: connection timed out after 5 seconds")
    except httpx.ConnectError:
        raise ValueError("Endpoint URL is unreachable: could not connect")
    except httpx.RequestError as exc:
        raise ValueError(f"Endpoint URL is unreachable: {exc}")

    if resp.status_code >= 500:
        raise ValueError(f"Endpoint returned server error (HTTP {resp.status_code})")

    return url


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint", mode="before")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        return _validate_endpoint_url(v.strip())


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
    return {"id": new_agent.id, "name": new_agent.name, "endpoint": new_agent.endpoint, "owner": user["address"]}


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
