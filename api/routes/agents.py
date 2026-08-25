"""Agent CRUD endpoints for the OpenAgents platform.
@contributor rafaio1
@timestamp 2026-08-25T02:05:00Z
@env linux x64 /tmp/openagents_issue_202 bash
@platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
"""

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
from fastapi import HTTPException



# --- URL Validation Helpers (Issue #187) ---
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def _validate_agent_endpoint(url: str) -> str:
    """Validate agent endpoint URL format, reachability, and SSRF safety."""
    # 1. Parse and validate format
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid URL format: {url}")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail=f"URL scheme must be http or https, got: {parsed.scheme}")
    if not parsed.hostname:
        raise HTTPException(status_code=422, detail="URL missing hostname")

    # 2. Resolve DNS and check for private/internal IPs (SSRF protection)
    try:
        addr_info = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=422, detail=f"Cannot resolve hostname: {parsed.hostname}")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Private/internal IP addresses are not allowed: {ip_str}"
                    )
        except ValueError:
            pass

    # 3. HEAD request to verify reachability (5s timeout)
    try:
        resp = httpx.head(url, timeout=5.0, follow_redirects=True)
        if resp.status_code >= 500:
            raise HTTPException(
                status_code=422,
                detail=f"Endpoint returned server error (HTTP {resp.status_code})"
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail=f"Endpoint unreachable (timeout after 5s): {url}")
    except httpx.ConnectError:
        raise HTTPException(status_code=422, detail=f"Cannot connect to endpoint: {url}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Endpoint validation failed: {str(e)}")

    return url


router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    endpoint: str  # Validated via _validate_agent_endpoint before DB insert
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = _validate_agent_endpoint(agent.endpoint)
    new_agent = Agent(
        name=agent.name,
        endpoint=validated_endpoint,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
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
