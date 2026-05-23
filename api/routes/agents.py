"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import socket
import struct
import aiohttp

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    endpoint: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator("name")
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @validator("endpoint")
    def validate_endpoint(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must be http or https URL")
        if not parsed.netloc:
            raise ValueError("Invalid URL: no host")
        try:
            host = parsed.hostname
            if host is None:
                raise ValueError("Invalid URL: no hostname")
            if host == "localhost" or host == "127.0.0.1" or host == "::1":
                raise ValueError("Localhost not allowed")
            if host.endswith(".local") or host.endswith(".internal"):
                raise ValueError("Internal hostnames not allowed")
            try:
                addr = socket.getaddrinfo(host, 80)[0][4][0]
                ip_int = struct.unpack("!I", socket.inet_aton(addr))[0]
                b1 = (ip_int >> 24) & 0xFF
                if b1 == 10 or b1 == 127 or (b1 == 192 and (ip_int >> 16) & 0xFF == 168) or (b1 == 172 and 16 <= (ip_int >> 16) & 0xFF <= 31):
                    raise ValueError("Private IP ranges not allowed")
            except (socket.gaierror, OSError, struct.error):
                pass
        except ValueError:
            raise
        except Exception:
            raise ValueError("Invalid URL: cannot resolve host")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


async def verify_endpoint_reachable(endpoint: str, timeout: int = 5) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(endpoint, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                return True
    except Exception:
        return False


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    reachable = await verify_endpoint_reachable(agent.endpoint)
    if not reachable:
        raise HTTPException(status_code=400, detail="Agent endpoint is not reachable")
    new_agent = Agent(
        name=agent.name,
        endpoint=agent.endpoint,
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
    return {"deleted": True}
