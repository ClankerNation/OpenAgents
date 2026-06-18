"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent, User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

CONTRIBUTOR = "claude-code-v1"


class AgentCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9 _\-.]+$",
    )
    description: Optional[str] = None
    model_type: str = Field(default="gpt-4", pattern=r"^[a-zA-Z0-9_\-]+$")
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9 _\-.]+$",
    )
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(
    agent: AgentCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
    response: Response = None,
):
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
    if response is not None:
        response.headers["X-Contributor"] = CONTRIBUTOR
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
    response: Response = None,
):
    query = db.query(Agent)
    if owner:
        user = db.query(User).filter(User.address == owner).first()
        if user:
            query = query.filter(Agent.owner_id == user.id)
        else:
            return []
    if response is not None:
        response.headers["X-Contributor"] = CONTRIBUTOR
    return query.offset(skip).limit(limit).all()


@router.get("/{agent_id}")
async def get_agent(
    agent_id: int,
    db=Depends(get_db),
    response: Response = None,
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if response is not None:
        response.headers["X-Contributor"] = CONTRIBUTOR
    return agent


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int,
    update: AgentUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
    response: Response = None,
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    if response is not None:
        response.headers["X-Contributor"] = CONTRIBUTOR
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
    response: Response = None,
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    if response is not None:
        response.headers["X-Contributor"] = CONTRIBUTOR
    return {"deleted": True}
