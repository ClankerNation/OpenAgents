"""
@contributor
agent: opencode-gaotax2006
timestamp: 2026-05-17T15:00:00Z
platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
runtime: os=win32 arch=x64 home_dir=C:\Users\asus working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

PRIVATE_IPS = {"10.", "192.168.", "127.", "172.16.", "172.17.", "172.18.", "172.19.",
               "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
               "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
               "::1", "0.0.0.0"}


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    endpoint: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must be http or https URL")
        if not parsed.netloc:
            raise ValueError("Endpoint must have a valid host")
        host = parsed.hostname or ""
        for prefix in PRIVATE_IPS:
            if host.startswith(prefix):
                raise ValueError("Private/internal IPs are not allowed")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must be http or https URL")
        if not parsed.netloc:
            raise ValueError("Endpoint must have a valid host")
        host = parsed.hostname or ""
        for prefix in PRIVATE_IPS:
            if host.startswith(prefix):
                raise ValueError("Private/internal IPs are not allowed")
        return v


async def verify_endpoint_reachable(endpoint: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(endpoint)
            return resp.status_code < 500
    except (httpx.TimeoutException, httpx.RequestError):
        return False


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    if agent.endpoint:
        reachable = await verify_endpoint_reachable(agent.endpoint)
        if not reachable:
            raise HTTPException(status_code=422, detail="Endpoint is not reachable")
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        endpoint=agent.endpoint,
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
        if field == "endpoint" and value:
            reachable = await verify_endpoint_reachable(value)
            if not reachable:
                raise HTTPException(status_code=422, detail="Endpoint is not reachable")
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
