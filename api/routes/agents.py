"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import ipaddress
import socket

import httpx

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


def _validate_and_normalize_public_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="endpoint must be a valid http/https URL")
    if not parsed.netloc:
        raise HTTPException(status_code=422, detail="endpoint must include a hostname")

    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=422, detail="endpoint hostname is invalid")

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror:
        raise HTTPException(status_code=422, detail="endpoint hostname cannot be resolved")

    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise HTTPException(status_code=422, detail="endpoint resolves to a private/internal IP")

    return url


async def _ensure_reachable(url: str) -> None:
    timeout = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                raise HTTPException(status_code=422, detail=f"endpoint is not reachable (HEAD {response.status_code})")
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail="endpoint HEAD check timed out")
    except httpx.HTTPError:
        raise HTTPException(status_code=422, detail="endpoint is not reachable")


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    endpoint = _validate_and_normalize_public_url(agent.endpoint)
    await _ensure_reachable(endpoint)

    payload_config = dict(agent.config or {})
    payload_config["endpoint"] = endpoint

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=payload_config,
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
        "endpoint": endpoint,
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
