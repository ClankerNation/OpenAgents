"""Agent CRUD endpoints for the OpenAgents platform.

@contributor codex-gpt5
@platform Codex Desktop session bootstrap (platform-managed initialization context)
@runtime Windows 11 x64, cwd=F:/jiedan/OpenAgents
@date 2026-05-31T03:41:14Z
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent, User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _serialize_agent(agent: Agent) -> dict:
    return {
        "id": agent.uuid,
        "name": agent.name,
        "description": agent.description,
        "model_type": agent.model_type,
        "config": agent.config,
        "owner": agent.owner.uuid if agent.owner else None,
        "created_at": agent.created_at,
    }


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
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
    return {"id": new_agent.uuid, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        query = query.join(User, Agent.owner_id == User.id).filter(User.uuid == owner)
    agents = query.offset(skip).limit(limit).all()
    return [_serialize_agent(agent) for agent in agents]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uuid == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _serialize_agent(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.uuid == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent)


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uuid == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    deleted_uuid = agent.uuid
    db.delete(agent)
    db.commit()
    return {"deleted": True, "id": deleted_uuid}
