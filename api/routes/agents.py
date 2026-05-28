"""Agent CRUD endpoints for the OpenAgents platform."""

import asyncio
import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in BLOCKED_NETWORKS)
    except ValueError:
        return False


def _validate_endpoint_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail="Endpoint must be an http or https URL",
        )
    if not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Endpoint must have a valid hostname",
        )
    if _is_private_ip(parsed.hostname):
        raise HTTPException(
            status_code=422,
            detail="Endpoint must not point to a private/internal IP address",
        )
    return url


async def _check_reachability(url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code >= 500:
                raise HTTPException(
                    status_code=422,
                    detail=f"Endpoint returned server error: {response.status_code}",
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=422,
            detail="Endpoint is not reachable (timeout after 5 seconds)",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=422,
            detail="Endpoint is not reachable (connection refused)",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Endpoint is not reachable",
        )


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint: str
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name must not be empty")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_no_injection(cls, v: str) -> str:
        dangerous = ["<", ">", "script", "javascript:", "onerror"]
        lower = v.lower()
        for pattern in dangerous:
            if pattern in lower:
                raise ValueError("Name contains invalid characters")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    _validate_endpoint_url(agent.endpoint)
    await _check_reachability(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
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
    limit: int = Query(50, ge=1, le=100),
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
        _validate_endpoint_url(update.endpoint)
        await _check_reachability(update.endpoint)

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
