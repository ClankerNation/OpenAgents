"""
@fix-author elevasyncsolutions-jpg
@date 2026-07-15
@platform-config Autonomous AI agent operating on macOS (arm64) with zsh.
  Agent: opencode (opencode/deepseek-v4-flash-free).
  Task: Validate endpoint URL format on register_agent with SSRF protection.
  Environment: CLI-only, no browser automation. Working dir: /Users/machd/ai-work/zbbaba_finals.
  Tools: Python3, curl, FastAPI, httpx, SQLAlchemy. Payment: USDC on Base (0xACCE0F0D...).
  Constraints: npm install times out. Cannot run tests. Must push verified code.
@runtime os: darwin, arch: arm64, home_dir: /Users/machd, working_dir: /Users/machd/ai-work/zbbaba_finals, shell: zsh
"""
"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import httpx
import ipaddress
import socket

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

PRIVATE_BLOCKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


class AgentCreate(BaseModel):
    name: str
    endpoint: Optional[str] = None
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator("name")
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        if len(v) > 100:
            raise ValueError("name too long (max 100)")
        return v.strip()

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("endpoint must be http or https URL")
        if not parsed.netloc:
            raise ValueError("endpoint must have a valid host")
        host = parsed.hostname
        try:
            addr = socket.gethostbyname(host)
            ip = ipaddress.ip_address(addr)
            for block in PRIVATE_BLOCKS:
                if ip in block:
                    raise ValueError("private/internal IPs not allowed")
        except socket.gaierror:
            pass
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    if agent.endpoint:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(agent.endpoint, follow_redirects=True)
                if resp.status_code >= 400:
                    raise HTTPException(status_code=400, detail=f"endpoint unreachable (status {resp.status_code})")
        except httpx.TimeoutException:
            raise HTTPException(status_code=400, detail="endpoint connection timed out")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"endpoint connection failed: {e}")
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
    return {"id": new_agent.id, "name": new_agent.name, "endpoint": agent.endpoint, "owner": user["address"]}


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
