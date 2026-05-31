"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    endpoint: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


def _is_internal_ip(ip_value: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    return (
        ip_value.is_private
        or ip_value.is_loopback
        or ip_value.is_link_local
        or ip_value.is_reserved
        or ip_value.is_multicast
    )


async def validate_agent_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Invalid endpoint URL format. Use a full http:// or https:// URL.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Endpoint URL must include a hostname.")

    try:
        direct_ip = ipaddress.ip_address(hostname)
        if _is_internal_ip(direct_ip):
            raise HTTPException(
                status_code=400,
                detail="Endpoint URL points to a private or internal IP address.",
            )
    except ValueError:
        if hostname.lower() == "localhost":
            raise HTTPException(
                status_code=400,
                detail="Endpoint URL points to a private or internal IP address.",
            )
        try:
            resolved_hosts = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Endpoint hostname could not be resolved.")

        for _, _, _, _, sockaddr in resolved_hosts:
            resolved_ip = ipaddress.ip_address(sockaddr[0].split("%")[0])
            if _is_internal_ip(resolved_ip):
                raise HTTPException(
                    status_code=400,
                    detail="Endpoint URL points to a private or internal IP address.",
                )

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            await client.head(normalized)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Endpoint URL check timed out after 5 seconds.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint URL is not reachable: {exc.__class__.__name__}.",
        )

    return normalized


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = await validate_agent_endpoint(agent.endpoint)
    config = dict(agent.config or {})
    config["endpoint"] = validated_endpoint

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=config,
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
