# @contributor-info rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
import urllib.parse
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False


async def validate_endpoint_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Endpoint must be http or https")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: missing hostname")

    # Resolve hostname and check for private IPs (SSRF protection)
    try:
        import socket
        infos = await asyncio.get_event_loop().run_in_executor(
            None, lambda: socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        )
        for info in infos:
            ip = info[4][0]
            if is_private_ip(ip):
                raise HTTPException(status_code=400, detail=f"Private/internal IP not allowed: {ip}")
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Cannot resolve hostname: {hostname}")

    # HEAD request to verify reachability
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.head(url)
            if resp.status_code >= 500:
                raise HTTPException(status_code=400, detail=f"Endpoint returned server error: {resp.status_code}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Endpoint unreachable: timeout after 5s")
    except httpx.ConnectError:
        raise HTTPException(status_code=400, detail="Endpoint unreachable: connection refused")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Endpoint validation failed: {str(e)}")

    return url


import asyncio


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Name cannot be empty")
        if len(v) > 64:
            raise ValueError("Name too long (max 64 chars)")
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    validated_endpoint = await validate_endpoint_url(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.now(timezone.utc),
        endpoint=validated_endpoint,
        active=True,
        deleted_at=None,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    include_inactive: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if not include_inactive:
        query = query.filter(Agent.active == True, Agent.deleted_at == None)
    if owner:
        query = query.filter(Agent.owner_id == owner)
    agents = query.offset(skip).limit(limit).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "model_type": a.model_type,
            "owner_id": a.owner_id,
            "created_at": a.created_at,
            "active": a.active,
            "endpoint": a.endpoint,
        }
        for a in agents
    ]


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent or agent.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent or agent.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")

    if update.endpoint is not None:
        update.endpoint = await validate_endpoint_url(update.endpoint)

    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent or agent.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    agent.active = False
    agent.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"deleted": True, "deleted_at": agent.deleted_at}
