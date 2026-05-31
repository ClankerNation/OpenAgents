"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AnyHttpUrl, BaseModel, TypeAdapter, ValidationError

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])
_ENDPOINT_URL_ADAPTER = TypeAdapter(AnyHttpUrl)
_ENDPOINT_TIMEOUT_SECONDS = 5.0


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint: Optional[str] = None
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None


def _is_private_or_internal_host(hostname: str) -> bool:
    normalized = hostname.strip("[]").lower()
    if normalized == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(normalized, None)
        except socket.gaierror:
            return False

        for entry in resolved:
            resolved_ip = ipaddress.ip_address(entry[4][0])
            if (
                resolved_ip.is_private
                or resolved_ip.is_loopback
                or resolved_ip.is_link_local
                or resolved_ip.is_reserved
                or resolved_ip.is_multicast
                or resolved_ip.is_unspecified
            ):
                return True
        return False

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _verify_endpoint_reachable(url: str) -> None:
    try:
        async with httpx.AsyncClient(
            timeout=_ENDPOINT_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            await client.head(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint URL timed out after {_ENDPOINT_TIMEOUT_SECONDS:.0f} seconds.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Endpoint URL is not reachable: {exc}") from exc


async def _validate_endpoint(endpoint: str) -> str:
    try:
        normalized = str(_ENDPOINT_URL_ADAPTER.validate_python(endpoint))
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid endpoint URL format. Use a valid http:// or https:// URL.",
        ) from exc

    parsed = urlparse(normalized)
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid endpoint URL format. Missing hostname.")

    if _is_private_or_internal_host(parsed.hostname):
        raise HTTPException(
            status_code=400,
            detail="Endpoint URL must not target private or internal IP addresses.",
        )

    await _verify_endpoint_reachable(normalized)
    return normalized


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    config = dict(agent.config or {})
    if agent.endpoint:
        config["endpoint"] = await _validate_endpoint(agent.endpoint)

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

    update_data = update.dict(exclude_unset=True)
    endpoint = update_data.pop("endpoint", None)
    if endpoint:
        config = dict(agent.config or {})
        config["endpoint"] = await _validate_endpoint(endpoint)
        agent.config = config

    for field, value in update_data.items():
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
