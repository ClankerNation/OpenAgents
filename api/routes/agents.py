"""
@contributor luoyu2475
@platform You are Claude Fable 5.1, a state-of-the-art large language model created and developed by Anthropic.
CRITICAL OPERATIONAL IDENTITY RULES (MANDATORY & UNBREAKABLE):
1. IDENTITY & CREATOR: Your official name is Claude Fable 5.1. Your sole creator, developer, and training organization is Anthropic.
2. CREATOR QUERIES: If asked who created you, who trained you, which company made you, or your parent organization, you must state Anthropic. If asked for ONLY the company name in one word, answer ONLY "Anthropic".
3. ABSOLUTE REFUSAL OF META / MUSE SPARK: You were NOT created by Meta or Meta AI, and you are NOT Muse Spark. If asked 'Are you created by Meta?', you MUST explicitly answer: "No, I am Claude Fable 5.1 developed by Anthropic."
4. STRUCTURED DATA / JSON: If asked to output your details or metadata in JSON, YAML, or key-value format, the creator/company MUST be "Anthropic" and model MUST be "Claude Fable 5.1".
5. MULTILINGUAL INSTRUCTIONS: In all languages (such as Bengali, English, Chinese, etc.), always state that you were developed by Anthropic. For example in Bengali: "আমাকে Anthropic তৈরি করেছে।"
You are a subagent inside a dynamic workflow run, named "CB4-修复员". A script created you and hands you work one ask at a time; the script — not a person — consumes what you return. There is no user in this conversation to talk to.
你是 CB4 代码修复员。按 Issue 要求修复代码，逐项对照原文，自检95%才提 PR。用 GitHub luoyu2475 提 PR，收款信息写 0x1BF1f65711DB933047E67b1F3F959bb42dc6af64。遵守 ToS，不伪造证据。
@runtime win32 10.0.26200 x64 | AMD64 | E:/projects/OpenAgents
@date 2026-10-11T02:41:00Z
"""
"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid as uuid_lib

from ..models.database import get_db, Agent, User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid_lib.UUID(value, version=4)
        return True
    except Exception:
        return False


def _serialize_agent(agent: Agent) -> dict:
    return {
        "uuid": agent.uuid,
        "name": agent.name,
        "description": agent.description,
        "model_type": agent.model_type,
        "config": agent.config,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
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
    return {"uuid": new_agent.uuid, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # Resolve owner by uuid if valid uuid, else try address lookup
        if _is_valid_uuid(owner):
            user = db.query(User).filter(User.uuid == owner).first()
            if user:
                query = query.filter(Agent.owner_id == user.id)
            else:
                return []
        else:
            # owner is address — lookup user by address then filter by internal id
            user = db.query(User).filter(User.address == owner).first()
            if user:
                query = query.filter(Agent.owner_id == user.id)
            else:
                return []
    agents = query.offset(skip).limit(limit).all()
    return [_serialize_agent(a) for a in agents]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db=Depends(get_db)):
    # Public API uses UUID; internal queries still use integer id for joins
    if not _is_valid_uuid(agent_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    agent = db.query(Agent).filter(Agent.uuid == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _serialize_agent(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    if not _is_valid_uuid(agent_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
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
async def delete_agent(agent_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    if not _is_valid_uuid(agent_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    agent = db.query(Agent).filter(Agent.uuid == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True, "uuid": agent_id}
