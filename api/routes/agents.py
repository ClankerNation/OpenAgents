"""Agent CRUD endpoints for the OpenAgents platform."""

import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


def _validate_endpoint_url(url: str) -> None:
    """Validate agent endpoint URL with SSRF protection."""
    if not url or not isinstance(url, str):
        return  # endpoint is optional

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are allowed for agent endpoint"
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Invalid endpoint URL: missing hostname"
        )

    hostname = parsed.netloc.split(":")[0].lower()

    # Block private/reserved IPs and localhost to prevent SSRF
    private_patterns = (
        r"^127\.",         # loopback
        r"^10\.",          # RFC 1918
        r"^172\.1[6-9]\.",
        r"^172\.2[0-9]\.",
        r"^172\.3[0-1]\.",
        r"^192\.168\.",    # RFC 1918
        r"^0\.0\.0\.0",
        r"^169\.254\.",    # link-local
        r"^localhost$",
        r"^\[::1\]$",      # IPv6 loopback
    )
    if re.match("|".join(private_patterns), hostname):
        raise HTTPException(
            status_code=400,
            detail="Endpoint URL resolves to a private address (SSRF protection)"
        )


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Validate endpoint URL in config before storing
    endpoint = (agent.config or {}).get("endpoint")
    if endpoint:
        _validate_endpoint_url(endpoint)

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
