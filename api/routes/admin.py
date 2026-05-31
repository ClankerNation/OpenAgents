"""Admin endpoints with immutable audit logging."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

try:
    from ..models.database import AuditLog, Agent, User, get_db
except ImportError:  # pragma: no cover
    from models.database import AuditLog, Agent, User, get_db


router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None


class AdminAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model_type: Optional[str] = None
    config: Optional[dict] = None


def require_admin_actor(request: Request) -> str:
    actor = request.headers.get("X-Admin-Actor")
    role = request.headers.get("X-Admin-Role", "")
    if not actor:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Actor header")
    if role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return actor


def _write_audit_log(
    *,
    db,
    action: str,
    actor: str,
    target: str,
    before_values: Optional[dict],
    after_values: Optional[dict],
    ip: Optional[str],
) -> None:
    log = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_values=before_values,
        after_values=after_values,
        timestamp=datetime.utcnow(),
        ip=ip,
    )
    db.add(log)


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    update: AdminUserUpdate,
    request: Request,
    actor: str = Depends(require_admin_actor),
    db=Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = update.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    before = {"username": user.username}
    for field, value in updates.items():
        setattr(user, field, value)
    after = {"username": user.username}

    _write_audit_log(
        db=db,
        action="user.update",
        actor=actor,
        target=f"user:{user.id}",
        before_values=before,
        after_values=after,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username}


@router.patch("/agents/{agent_id}")
async def admin_update_agent(
    agent_id: int,
    update: AdminAgentUpdate,
    request: Request,
    actor: str = Depends(require_admin_actor),
    db=Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    updates = update.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    before = {
        "name": agent.name,
        "description": agent.description,
        "model_type": agent.model_type,
        "config": agent.config,
    }
    for field, value in updates.items():
        setattr(agent, field, value)
    after = {
        "name": agent.name,
        "description": agent.description,
        "model_type": agent.model_type,
        "config": agent.config,
    }

    _write_audit_log(
        db=db,
        action="agent.update",
        actor=actor,
        target=f"agent:{agent.id}",
        before_values=before,
        after_values=after,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(agent)
    return {"id": agent.id, "name": agent.name, "model_type": agent.model_type}


@router.get("/audit-log")
async def get_audit_log(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
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

    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor": log.actor,
            "target": log.target,
            "before_values": log.before_values,
            "after_values": log.after_values,
            "timestamp": log.timestamp.isoformat(),
            "ip": log.ip,
        }
        for log in logs
    ]
