"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from datetime import datetime
from typing import Optional, Union
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])
ENDPOINT_TIMEOUT_SECONDS = 5.0


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


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _is_private_or_internal_ip(ip: IPAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_public_endpoint_host(hostname: str) -> None:
    if hostname.lower() == "localhost":
        raise HTTPException(status_code=400, detail="Endpoint URL cannot use localhost")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise HTTPException(status_code=400, detail="Endpoint host could not be resolved") from exc

        for _, _, _, _, sockaddr in resolved:
            resolved_ip = ipaddress.ip_address(sockaddr[0])
            if _is_private_or_internal_ip(resolved_ip):
                raise HTTPException(
                    status_code=400,
                    detail=f"Endpoint URL resolves to private/internal IP: {resolved_ip}",
                )
        return

    if _is_private_or_internal_ip(ip):
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint URL cannot use private/internal IP: {ip}",
        )


async def _validate_endpoint_url(endpoint: str) -> str:
    candidate = endpoint.strip()
    parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Endpoint URL must use http or https")
    if not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Endpoint URL must include a host")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Endpoint URL cannot contain credentials")

    _validate_public_endpoint_host(parsed.hostname)

    try:
        async with httpx.AsyncClient(timeout=ENDPOINT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            await client.head(candidate)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint URL timed out after {int(ENDPOINT_TIMEOUT_SECONDS)}s",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=400, detail=f"Endpoint URL is unreachable: {exc}") from exc

    return candidate


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = await _validate_endpoint_url(agent.endpoint)
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
