"""
@fix-author rafaio1
@date 2026-08-20T00:00:00Z
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/internal IP (SSRF protection)."""
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip_str = info[4][0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except socket.gaierror:
        return True  # If we can't resolve, treat as unsafe
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
            raise ValueError("Agent name cannot be empty")
        if len(v) > 255:
            raise ValueError("Agent name too long")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            parsed = urlparse(v)
        except Exception:
            raise ValueError("Invalid URL format")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must use http or https scheme")
        if not parsed.hostname:
            raise ValueError("Endpoint missing hostname")
        if _is_private_ip(parsed.hostname):
            raise ValueError("Private/internal IPs are not allowed")
        return v


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
        try:
            parsed = urlparse(v)
        except Exception:
            raise ValueError("Invalid URL format")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must use http or https scheme")
        if not parsed.hostname:
            raise ValueError("Endpoint missing hostname")
        if _is_private_ip(parsed.hostname):
            raise ValueError("Private/internal IPs are not allowed")
        return v


async def _verify_endpoint_reachable(endpoint: str) -> None:
    """HEAD request to verify endpoint is reachable (5s timeout)."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.head(endpoint)
            # Accept any response (even 4xx) as "reachable"
            if resp.status_code >= 500:
                raise HTTPException(
                    status_code=422,
                    detail=f"Endpoint returned server error ({resp.status_code})",
                )
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail="Endpoint unreachable (timeout)")
    except httpx.ConnectError:
        raise HTTPException(status_code=422, detail="Endpoint unreachable (connection refused)")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Endpoint verification failed: {str(e)}")


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    if agent.endpoint:
        await _verify_endpoint_reachable(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    if agent.endpoint:
        new_agent.endpoint = agent.endpoint
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

    if update.endpoint is not None:
        await _verify_endpoint_reachable(update.endpoint)

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
    return {"deleted": True}
