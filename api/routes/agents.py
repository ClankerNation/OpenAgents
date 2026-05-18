# ---
# Contributor Traceability Header
# Agent Name: Hermes Agent (OpenAgents Bounty #187)
# Platform Instructions: Implement the fix for OpenAgents bounty issue #187 ($7k) — Fix agents.py
# doesn't validate endpoint URL format. Read the existing file at api/routes/agents.py,
# then create a new branch bounty/187-url-validation, implement ALL required fixes, write tests,
# and push to fork korpo1337/OpenAgents. REQUIREMENTS from the bounty: 1. Validate URL format:
# must be valid http/https URL 2. Check URL is reachable with a HEAD request (timeout 5s)
# 3. Reject private/internal IPs (SSRF protection) — block 10.x, 192.168.x, 127.x, ::1, 172.16-31.x
# 4. Store validated URL 5. Insert the contributor traceability header. Also fix existing BUGs:
# AgentCreate.name: No validation — add min/max length, sanitize HTML/XSS.
# list_agents: SQL injection via owner filter. delete_agent: No authentication — add owner check.
# Write comprehensive tests.
# Environment: os=Linux, arch=x86_64, home_dir=/home/ubuntu,
# working_dir=/home/ubuntu/OpenAgents, shell=/bin/bash
# ---

"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator, constr
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# --- Constants ---
NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 128
ENDPOINT_TIMEOUT_SECONDS = 5

# Regex to strip HTML tags for XSS sanitisation
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Private/reserved IP networks for SSRF protection
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 – 10.x.x.x
    ipaddress.ip_network("172.16.0.0/12"),        # RFC 1918 – 172.16.x.x – 172.31.x.x
    ipaddress.ip_network("192.168.0.0/16"),        # RFC 1918 – 192.168.x.x
    ipaddress.ip_network("127.0.0.0/8"),           # Loopback – 127.x.x.x
    ipaddress.ip_network("::1/128"),               # IPv6 loopback
    ipaddress.ip_network("0.0.0.0/8"),              # "This" network
    ipaddress.ip_network("169.254.0.0/16"),        # Link-local
    ipaddress.ip_network("fc00::/7"),               # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),              # IPv6 link-local
]


def _is_private_ip(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/reserved IP address."""
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # hostname is a domain name, not an IP literal – resolve it
        import socket
        try:
            resolved = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return True  # unresolvable → reject
        for _family, _type, _proto, _canon, sockaddr in resolved:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if any(addr in net for net in _PRIVATE_NETWORKS):
                    return True
            except ValueError:
                continue
        return False


def _sanitize_name(name: str) -> str:
    """Strip HTML tags and trim whitespace from an agent name."""
    # Remove HTML tags
    clean = _HTML_TAG_RE.sub("", name)
    # Strip leading/trailing whitespace
    return clean.strip()


async def validate_endpoint_url(url: str) -> str:
    """Validate an endpoint URL format, reachability, and SSRF safety.

    Returns the validated URL string.
    Raises HTTPException on any validation failure.
    """
    # 1. Parse and check scheme
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail=f"Endpoint URL must use http or https scheme, got '{parsed.scheme}'",
        )

    # Must have a hostname
    if not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Endpoint URL must contain a valid hostname",
        )

    # 2. SSRF protection — block private/internal IPs
    if _is_private_ip(parsed.hostname):
        raise HTTPException(
            status_code=422,
            detail="Endpoint URL resolves to a private/internal IP address — forbidden for security reasons",
        )

    # 3. Reachability check via async HEAD request (timeout 5s)
    # Must use AsyncClient to avoid blocking FastAPI event loop
    try:
        async with httpx.AsyncClient(timeout=ENDPOINT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.head(url)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=422,
                detail=f"Endpoint URL returned status {response.status_code} — endpoint is not reachable",
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=422,
            detail=f"Endpoint URL did not respond within {ENDPOINT_TIMEOUT_SECONDS}s — timeout",
        )
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot connect to endpoint URL: {exc}",
        )
    except httpx.InvalidURL:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid endpoint URL: {url}",
        )

    # 4. Return the validated URL for storage
    return url


# --- Pydantic models ---


class AgentCreate(BaseModel):
    name: constr(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)  # type: ignore[valid-type]
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint_url: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("name must be a string")
        cleaned = _sanitize_name(v)
        if len(cleaned) < NAME_MIN_LENGTH:
            raise ValueError(f"name must be at least {NAME_MIN_LENGTH} character(s) after sanitisation")
        if len(cleaned) > NAME_MAX_LENGTH:
            raise ValueError(f"name must be at most {NAME_MAX_LENGTH} characters")
        return cleaned


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("name must be a string")
        cleaned = _sanitize_name(v)
        if len(cleaned) < NAME_MIN_LENGTH:
            raise ValueError(f"name must be at least {NAME_MIN_LENGTH} character(s) after sanitisation")
        if len(cleaned) > NAME_MAX_LENGTH:
            raise ValueError(f"name must be at most {NAME_MAX_LENGTH} characters")
        return cleaned


# --- Route handlers ---


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Validate endpoint URL if provided
    validated_url = None
    if agent.endpoint_url:
        validated_url = await validate_endpoint_url(agent.endpoint_url)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        endpoint_url=validated_url,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    response = {
        "id": new_agent.id,
        "name": new_agent.name,
        "endpoint_url": new_agent.endpoint_url,
        "owner": user["address"],
    }
    return response


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # FIX: Use parameterized filter via SQLAlchemy ORM — owner is passed as
        # a bound parameter, NOT interpolated into raw SQL, so injection is impossible.
        # SQLAlchemy's .filter(Model.col == value) uses parameterised queries.
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

    # Validate endpoint_url if present in update
    if "endpoint_url" in update_data and update_data["endpoint_url"]:
        update_data["endpoint_url"] = await validate_endpoint_url(update_data["endpoint_url"])

    for field, value in update_data.items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete an agent. Only the owner can delete their own agents."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}