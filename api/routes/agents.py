# @contributor ahmedabdelkarim504-commits
# @platform-config Agent protocol: Read Brain Home.md first. Read E:\AiLab\Obsidian Vault\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion. Agent Memory System (cross-session): Run agent_memory.py summary on session start. Vault RAG: Use vault_rag.py for context. Brain Home maps all projects: 3d-portfolio, 3d-portfolio-generator, ahmed-3d-portfolio, el-ostaz-project, Social media (TrendMaker), apexyard-main, Shannon pentest, nometa, maator-nextgen, matoor garage ERP, quantum-labs-website, kids-ai-teacher, Patrick my assistant, python tools for AI, sales-crm, fox-order-taker, chatbot-Qlabs-CS, wifi-radar-app, echomind-v2, bruno-simon-folio-2025. Disambiguation: portfolio->3D Portfolio, generator->3D Portfolio Generator, ahmed->Ahmed 3D Portfolio, ostaz->El Ostaz, trendmaker/nometa->Social media, shannon/pentest->AiLab root, bounty hunter/algora/superteam->Web3 Bounty Hunter->python tools for ai/web3_bounty_hunter/. Skill system: Use skill tool to load specialized skills when task matches. Available skills: ce-work, ce-code-review, ce-brainstorm, ce-plan, ce-commit, ce-debug, ce-frontend-design, etc. Brainstem: 1,963 tools via MCP. Video editor+montage: 5 suites, 46 actions, ffmpeg. Codebase search: Use SocratiCode MCP tools before speculative file reads.
# @env {"os": "win32", "arch": "x64", "home_dir": "C:\\Users\\SS", "working_dir": "E:\\AiLab", "shell": "powershell.exe"}
# @timestamp 2026-07-17T15:00:00Z
"""Agent CRUD endpoints for the OpenAgents platform."""

import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Maximum allowed name length
MAX_NAME_LENGTH = 64
# Only allow alphanumeric, hyphens, underscores, and spaces
NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\s]+$')
# Pagination cap
MAX_PAGINATION_LIMIT = 100


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f'Name must be {MAX_NAME_LENGTH} characters or less')
        if not NAME_PATTERN.match(v):
            raise ValueError('Name can only contain alphanumeric characters, hyphens, underscores, and spaces')
        return v.strip()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError('Name cannot be empty')
            if len(v) > MAX_NAME_LENGTH:
                raise ValueError(f'Name must be {MAX_NAME_LENGTH} characters or less')
            if not NAME_PATTERN.match(v):
                raise ValueError('Name can only contain alphanumeric characters, hyphens, underscores, and spaces')
            return v.strip()
        return v


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
    limit: int = Query(50, ge=1, le=MAX_PAGINATION_LIMIT),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # Using parameterized query via SQLAlchemy ORM (safe from SQL injection)
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
    # FIX: Require authentication — only the owner can delete their agent
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
