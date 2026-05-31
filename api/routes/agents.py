"""Agent CRUD endpoints for the OpenAgents platform."""

from datetime import datetime
import ipaddress
import socket
from typing import Optional, Union
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

ENDPOINT_REACHABILITY_TIMEOUT_SECONDS = 5.0


def _validate_endpoint_url_format(endpoint: str):
    parsed = urlparse(endpoint.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must be a valid http/https URL",
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must not include URL credentials",
        )
    return parsed


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _resolve_hostname_addresses(hostname: str) -> list[IPAddress]:
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addrinfo = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise HTTPException(
                status_code=422,
                detail="Agent endpoint hostname could not be resolved",
            ) from exc
        resolved = []
        for _, _, _, _, sockaddr in addrinfo:
            resolved.append(ipaddress.ip_address(sockaddr[0]))
        return resolved


def _is_internal_address(address: IPAddress) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


async def validate_agent_endpoint(endpoint: str) -> str:
    parsed = _validate_endpoint_url_format(endpoint)
    resolved_addresses = _resolve_hostname_addresses(parsed.hostname)
    if any(_is_internal_address(address) for address in resolved_addresses):
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must not resolve to a private/internal IP",
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(ENDPOINT_REACHABILITY_TIMEOUT_SECONDS),
            follow_redirects=True,
        ) as client:
            response = await client.head(endpoint)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint is unreachable (request timed out)",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint is unreachable",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint is unreachable",
        )

    return endpoint


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
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "owner": user["address"],
        "endpoint": validated_endpoint,
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
