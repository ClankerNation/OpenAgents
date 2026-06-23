"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Strict URL regex for endpoint validation
_ENDPOINT_RE = re.compile(
    r'^https?://'
    r'[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?'
    r'(\.[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?)*'
    r'(:\d{1,5})?'
    r'(/[A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]*)?$'
)

# Private IP patterns to block (SSRF protection)
_PRIVATE_PATTERNS = [
    r'^https?://127\.',
    r'^https?://localhost',
    r'^https?://10\.',
    r'^https?://172\.(1[6-9]|2\d|3[01])\.',
    r'^https?://192\.168\.',
    r'^https?://0\.0\.0\.0',
    r'^https?://\[::1\]',
    r'^https?://\[fe80:',
]


class AgentCreate(BaseModel):
    """Schema for creating a new agent with validated endpoint."""

    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str  # HTTP(S) URL for agent communication

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip() or len(v) < 1:
            raise ValueError("Agent name must not be empty")
        if len(v) > 128:
            raise ValueError("Agent name must be <= 128 characters")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate endpoint URL format and SSRF protection."""
        if not _ENDPOINT_RE.match(v):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        for pattern in _PRIVATE_PATTERNS:
            if re.match(pattern, v, re.IGNORECASE):
                raise ValueError("Endpoint must not point to internal/private addresses")
        return v.lower()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _ENDPOINT_RE.match(v):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        for pattern in _PRIVATE_PATTERNS:
            if re.match(pattern, v, re.IGNORECASE):
                raise ValueError("Endpoint must not point to internal/private addresses")
        return v.lower()


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Optional: check endpoint reachability
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(agent.endpoint, allow_redirects=True)
            if resp.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"Endpoint unreachable: {resp.status_code}")
    except Exception:
        # Don't block registration if endpoint is temporarily down
        pass

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint=agent.endpoint,
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"], "endpoint": new_agent.endpoint}


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
