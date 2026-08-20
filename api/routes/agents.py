# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow
"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import field_validator, HttpUrl
import httpx
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    endpoint: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        if len(v) > 128:
            raise ValueError("Agent name too long (max 128 chars)")
        # Basic sanitization to prevent XSS/SQL injection vectors
        forbidden = ["<", ">", "'", '"', ";", "--", "/*", "*/"]
        for char in forbidden:
            if char in v:
                raise ValueError(f"Agent name contains forbidden character: {char}")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Endpoint URL cannot be empty")
        # Validate URL format using Pydantic's HttpUrl
        try:
            parsed = HttpUrl(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Endpoint must use http or https scheme")
        except Exception:
            raise ValueError("Invalid endpoint URL format")
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Verify endpoint is reachable with a HEAD request (timeout 5s)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(agent.endpoint)
            if response.status_code >= 500:
                raise HTTPException(status_code=400, detail=f"Endpoint returned server error: {response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Endpoint unreachable: {str(e)}")

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
