"""Agent CRUD endpoints for the OpenAgents platform."""
# @contributor-info: hermes-agent | bounty #183

import re
import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, constr
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Name validation constraints
NAME_MIN_LEN = 1
NAME_MAX_LEN = 128
NAME_PATTERN = re.compile(r"<[^>]+>")  # HTML/XSS tag detection


def _sanitize_name(name: str) -> str:
    """Strip HTML/XSS tags and trim whitespace from agent name."""
    cleaned = NAME_PATTERN.sub("", name).strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Agent name cannot be empty after sanitization")
    return cleaned


def _is_private_ip(hostname: str) -> bool:
    """Block SSRF: reject private/internal IPs."""
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # hostname is not an IP — check for internal-looking hostnames
        internal = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")
        return hostname in internal


async def validate_endpoint_url(url: str) -> str:
    """Validate endpoint URL: scheme, hostname, SSRF protection, and reachability."""
    parsed = urlparse(url)
    # Scheme check: only http(s) allowed
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail=f"Invalid URL scheme: {parsed.scheme}. Only http and https are allowed.")
    # Hostname required
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL must contain a hostname.")
    # SSRF protection: block private/internal IPs
    if _is_private_ip(parsed.hostname):
        raise HTTPException(status_code=400, detail="Endpoint URL points to a private/internal address. SSRF blocked.")
    # Reachability check via async HEAD request
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code >= 500:
                raise HTTPException(status_code=400, detail=f"Endpoint returned server error: {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=400, detail="Endpoint URL is not reachable.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Endpoint URL timed out.")
    return url


class AgentCreate(BaseModel):
    name: constr(min_length=1, max_length=128)  # FIX: enforce min/max length, no empty names
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint_url: Optional[str] = None  # NEW: optional endpoint URL for agent


class AgentUpdate(BaseModel):
    name: Optional[constr(min_length=1, max_length=128)] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint_url: Optional[str] = None  # NEW: optional endpoint URL for agent


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # FIX: Sanitize name to strip XSS/HTML tags
    sanitized_name = _sanitize_name(agent.name)

    # Validate endpoint URL if provided
    if agent.endpoint_url:
        await validate_endpoint_url(agent.endpoint_url)

    new_agent = Agent(
        name=sanitized_name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint_url=agent.endpoint_url,
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
    limit: int = Query(50, ge=1, le=100),  # FIX: add upper bound to limit
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # NOTE: SQLAlchemy ORM .filter() uses parameterized queries — not vulnerable to SQL injection
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

    # FIX: Sanitize name if provided
    if "name" in update_data:
        update_data["name"] = _sanitize_name(update_data["name"])

    # FIX: Validate endpoint URL if provided
    if "endpoint_url" in update_data and update_data["endpoint_url"]:
        await validate_endpoint_url(update_data["endpoint_url"])

    for field, value in update_data.items():
        setattr(agent, field, value)
    db.commit()
    return agent


# FIX: Added authentication — only owner can delete their agent
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