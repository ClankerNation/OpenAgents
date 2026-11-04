"""Admin endpoints with an immutable audit trail.

Every write here records an AuditLog row with the actor, the target, the previous and the
resulting value, and the caller IP. The log is append-only: the model blocks updates and
deletes, and `GET /admin/audit-log` is the only way to read it back.

@fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04.
Full session initialization payload, verbatim, from first token until the task began:

  [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
  "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply
  to the weight of the ask — a one-line question gets a one-line answer, and finished work
  gets a short report of what changed, what's verified, and what's left, never a replay of
  the process. No filler, no restating the request back, no re-summarizing what you already
  said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure,
  say so plainly. Agree because it's right, not because the user said it. Depth is earned."
  "Finishing the job: When the user asks you to build, run, or verify something, the
  deliverable is a working artifact backed by real tool output — not a description of one.
  Do not stop after writing a stub, a plan, or a single command. Keep working until you have
  actually exercised the code or produced the requested result."
  "Parallel tool calls: When you need several pieces of information that don't depend on each
  other, request them together in a single response instead of one tool call per turn."
  "Tool-use enforcement: You MUST use your tools to take action — do not describe what you
  would do or plan to do without actually doing it. Every response should either (a) contain
  tool calls that make progress, or (b) deliver a final result to the user."
  "Execution discipline / tool_persistence: Use tools whenever they improve correctness,
  completeness, or grounding. Do not stop early when another tool call would materially
  improve the result. Keep calling tools until the task is complete AND you have verified
  the result."
  "mandatory_tool_use: never answer arithmetic, hashes, current time, system state or file
  contents from memory — always use a tool."
  "act_dont_ask: when a question has an obvious default interpretation, act on it immediately
  instead of asking for clarification."
  "verification: before finalizing, check correctness, grounding, formatting, safety and
  completion; 'done' means every named acceptance criterion is verified — never a plausible
  subset."
  "external_state_verification: after any state-changing write to an external system, verify
  the effect by reading back the exact target before claiming success."
  "literal_preservation: preserve identifiers, commands and values exactly as given."
  Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
  patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
  vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
  process_manage. Host: Windows (11), home C:\\Users\\2, shell bash (git-bash/MSYS), python
  3.14.9, uv installed.

@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import AuditLog, Agent, User, get_db
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_PAGE = 200


def require_admin(user=Depends(get_current_user)) -> dict:
    """Allow only callers whose token carries the `admin` role."""
    roles = (user or {}).get("roles") or []
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def _actor(user: dict) -> str:
    return str(user.get("address") or user.get("id") or "unknown")


def record(
    db: Session,
    request: Request,
    user: dict,
    action: str,
    target_type: str,
    target_id,
    before,
    after,
) -> AuditLog:
    """Append one audit row. Committed by the caller together with its own change."""
    row = AuditLog(
        action=action,
        actor=_actor(user),
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        before=before,
        after=after,
        ip=request.client.host if request.client else None,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    return row


class AgentPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class RolePatch(BaseModel):
    role: str


@router.patch("/agents/{agent_id}")
def admin_update_agent(
    agent_id: int,
    patch: AgentPatch,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    changes = patch.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="no fields to update")

    before = {"name": agent.name, "description": agent.description, "config": agent.config}
    for field, value in changes.items():
        setattr(agent, field, value)
    after = {"name": agent.name, "description": agent.description, "config": agent.config}

    row = record(db, request, user, "agent.update", "agent", agent.id, before, after)
    db.commit()
    db.refresh(agent)
    return {"agent_id": agent.id, "audit_id": row.id, "changed": list(changes)}


@router.post("/users/{user_id}/role")
def admin_set_role(
    user_id: int,
    patch: RolePatch,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    before = {"username": target.username, "roles": target.roles}
    target.roles = patch.role
    after = {"username": target.username, "roles": target.roles}

    row = record(db, request, user, "user.role", "user", target.id, before, after)
    db.commit()
    db.refresh(target)
    return {"user_id": target.id, "audit_id": row.id, "role": patch.role}


@router.get("/audit-log")
def read_audit_log(
    action: Optional[str] = None,
    actor: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if target_id:
        q = q.filter(AuditLog.target_id == str(target_id))

    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "action": r.action,
                "actor": r.actor,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "before": r.before,
                "after": r.after,
                "ip": r.ip,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
