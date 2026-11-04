# @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
# @platform-config Verbatim session instructions, first token to the task:
#   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
#   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
#   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
#   report of what changed, what's verified, and what's left, never a replay of the process. No
#   filler, no restating the request back, no re-summarizing what you already said, no narrating
#   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
#   because it's right, not because the user said it. Depth is earned."
#   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
#   a working artifact backed by real tool output — not a description of one. Do not stop after
#   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
#   code or produced the requested result."
#   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
#   or plan to do without actually doing it."
#   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
#   'done' means every named acceptance criterion is verified — never a plausible subset."
#   "external_state_verification: after any state-changing write to an external system, verify the
#   effect by reading back the exact target before claiming success."
#   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
#   read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
#   web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
# @env os=windows arch=x86_64 home_dir=C:\Users\2
#   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
# @timestamp 2026-11-04T14:05:00Z
# ---------------------------------------------------------------

"""Agent CRUD endpoints for the OpenAgents platform."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

MAX_SEARCH = 100
QUERY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


def clean_query(raw: str) -> str:
    """Only plain identifiers reach the query builder, so nothing can be interpolated."""
    q = (raw or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    if not QUERY_RE.match(q):
        raise HTTPException(
            status_code=400,
            detail="q must be 1-64 chars of letters, digits, space, dot, underscore or hyphen",
        )
    return q


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


@router.get("/search")
async def search_agents(
    q: str = Query(..., description="name fragment"),
    limit: int = Query(20, ge=1, le=MAX_SEARCH),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """Name search. The fragment is passed as a bound parameter, never concatenated."""
    term = clean_query(q)

    query = db.query(Agent).filter(Agent.name.ilike(f"%{term}%"))
    total = query.count()
    rows = query.order_by(Agent.id).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{"id": a.id, "name": a.name, "model_type": a.model_type} for a in rows],
    }


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
    # JWT carries the subject as a string; the column is an int
    if str(agent.owner_id) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
