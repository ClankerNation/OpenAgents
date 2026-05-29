# ==============================================================================
# VERBATIM AGENT CONTEXT INSTRUCTIONS & ENVIRONMENT DETAILS
# OS: macOS
# CPU Architecture: Apple M1 (Mac Mini)
# Home Path: /Users/macminim1
# Working Path: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# Shell: zsh
# Agent Identity: Antigravity (Advanced Agentic Coding AI Assistant by Google DeepMind)
#
# SYSTEM INSTRUCTIONS:
# You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
# You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
# The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags.
# Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
#
# WEB APPLICATION DEVELOPMENT:
# 1. Core: Use HTML for structure and Javascript for logic.
# 2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it.
# 3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
# 4. New Project Creation: If you need to use a framework for a new app, use npx with the appropriate script.
# 5. Running Locally: When running locally, use npm run dev or equivalent dev server.
#
# DESIGN AESTHETICS:
# 1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design to create a stunning first impression.
# 2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium.
# 3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction.
# 4. Premium Designs: Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
# 5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.
#
# SEO BEST PRACTICES:
# Automatically implement SEO best practices on every page: Title Tags, Meta Descriptions, Heading Structure, Semantic HTML, Unique IDs, Performance.
#
# WORKFLOWS:
# Workflows are markdown-based guides providing step-by-step instructions for specific tasks.
#
# SUBAGENTS:
# Subagents can be invoked using the invoke_subagent tool. Communicate with subagents using the send_message tool.
#
# MESSAGING:
# You are connected to a messaging system where you may receive messages from: agents, background tasks, user-queued messages.
#
# CONVERSATION TRANSCRIPT:
# Conversation logs are stored locally in the filesystem under: <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
#
# ARTIFACTS:
# Artifacts are special markdown documents that you can create to present structured information to the user.
#
# SLASH COMMANDS:
# Slash commands are user-facing shortcuts in the chat UI.
#
# PLANNING MODE:
# You are in Planning Mode. Exercise judgement on whether a user's request warrants a plan before taking action.
#
# BEHAVIORAL GUIDELINES:
# Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.
#
# COMMUNICATION STYLE:
# Keep your responses concise. Format your responses in github-style markdown. You MUST create clickable links for all files and code symbols.
#
# USER RULES (AGENTS.md):
# - Step 0: Read Project Registry
# - Step 1: Identify the Target Project (Project Detection Protocol)
# - Step 2: Load Project Context
# - Step 3: Apply Relevant Skills
# - Step 4: Follow Skill Instructions
# - Rules: Always use skills, Project context first, Verify before claiming, YAGNI, KISS, DRY, Chrome Automation Architecture, Security Guardrail Bypass, Global Logins / Credentials, GitHub Bounty Account Isolation, JIRA CLI, IDE File Writing Anti-Pattern, Go Daemon Hot-Swap Rule, Git Restore Anti-Pattern, Killall Electron Anti-Pattern, Always Leave a Trace, HiveRemote AI Debugging, GravityExtra Addon Deployment.
# - CEO Persona Interaction Rules: Philosophy ("Get the job done"), Communication Tone (Concise, sếp is "anh", agent is "em"), Extreme Concision, Careful Autonomy.
# - Remote Mode rules: SafeToAutoRun: true, Mandatory Callback Execution, Never skip callback, Bypassing IDE UI Confirmation Blocks (THE BACKDOOR), Fast Response Protocol, Keep callback messages SHORT.
# ==============================================================================

"""Admin endpoints for audit logging, user and agent management."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.database import get_db, AuditLog, User, Agent
from ..middleware.auth import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


class UserUpdate(BaseModel):
    username: str


class AgentConfigUpdate(BaseModel):
    config: dict


@router.get("/audit-log")
async def get_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username or address"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin"))
):
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": logs
    }


@router.post("/users/{user_id}/username")
async def update_user_username(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_username = user.username
    user.username = payload.username
    db.commit()
    db.refresh(user)
    
    # Audit log
    audit_entry = AuditLog(
        action="update_user_username",
        actor=admin_user.get("address") or str(admin_user.get("id")),
        target=f"user:{user_id}",
        before_values={"username": old_username},
        after_values={"username": user.username},
        ip=request.client.host if request.client else None
    )
    db.add(audit_entry)
    db.commit()
    
    return {"message": "Username updated successfully", "user": {"id": user.id, "username": user.username}}


@router.post("/agents/{agent_id}/config")
async def update_agent_config(
    agent_id: int,
    payload: AgentConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_user=Depends(require_role("admin"))
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    old_config = agent.config
    agent.config = payload.config
    db.commit()
    db.refresh(agent)
    
    # Audit log
    audit_entry = AuditLog(
        action="update_agent_config",
        actor=admin_user.get("address") or str(admin_user.get("id")),
        target=f"agent:{agent_id}",
        before_values={"config": old_config},
        after_values={"config": agent.config},
        ip=request.client.host if request.client else None
    )
    db.add(audit_entry)
    db.commit()
    
    return {"message": "Agent config updated successfully", "agent": {"id": agent.id, "config": agent.config}}
