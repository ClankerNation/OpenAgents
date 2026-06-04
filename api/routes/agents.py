# Agent: MONAI Autonomous (szamaniai)
# Timestamp: 2026-06-04T21:30:00Z
# Startup: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
# Env: Linux x86_64, Python 3.12, /app, /app/api/routes

"""Agent CRUD endpoints for the OpenAgents platform."""

import http.client
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# RFC 1918 + RFC 6598 private ranges
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
]


def validate_agent_endpoint(url: str) -> str:
    """Validate agent endpoint URL: format, reachability, SSRF protection."""
    # Validate URL format
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint must use http or https scheme")
    if not parsed.netloc or "." not in parsed.netloc and "[" not in parsed.netloc:
        raise ValueError("Endpoint must have a valid hostname (e.g., example.com)")
    if not parsed.path and not parsed.netloc:
        raise ValueError("Invalid URL format")

    hostname = parsed.hostname
    # DNS resolution with timeout
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5)
        try:
            addrs = socket.getaddrinfo(hostname, None)
        finally:
            socket.setdefaulttimeout(old_timeout)
    except socket.gaierror:
        raise ValueError(f"Endpoint unreachable: cannot resolve hostname '{hostname}'")
    except OSError:
        raise ValueError(f"Endpoint unreachable: DNS resolution timed out for '{hostname}'")

    resolved_ips = []
    for addr in addrs:
        ip = addr[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            continue
        resolved_ips.append(ip)
        if any(ip_obj in net for net in _PRIVATE_RANGES):
            raise ValueError(f"Private IPs not allowed: {ip}")
        if ip_obj.is_loopback:
            raise ValueError(f"Loopback IPs not allowed: {ip}")
        if ip_obj.is_link_local:
            raise ValueError(f"Link-local IPs not allowed: {ip}")
        if ip_obj.is_multicast:
            raise ValueError(f"Multicast IPs not allowed: {ip}")
        if ip_obj.is_reserved:
            raise ValueError(f"Reserved IPs not allowed: {ip}")

    # Check reachability with HEAD request (timeout 5s) via http.client
    try:
        conn = http.client.HTTPConnection(hostname, timeout=5) if parsed.scheme == "http" \
            else http.client.HTTPSConnection(hostname, timeout=5)
        conn.request("HEAD", parsed.path or "/", headers={"Host": hostname})
        conn.getresponse()
        conn.close()
    except (http.client.HTTPException, socket.timeout, OSError) as e:
        raise ValueError(f"Endpoint unreachable: {e}")

    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v):
        if v is not None:
            return validate_agent_endpoint(v)
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v):
        if v is not None:
            return validate_agent_endpoint(v)
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    try:
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
        return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    return {"ok": True}
