# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:32:03+07:00

"""Admin router containing write endpoints and audit log viewer."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.database import get_db, User, AuditLog
from ..middleware.auth import require_role

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_CONFIG = {
    "maintenance_mode": "false",
    "min_reward_wei": "1000",
}


class ConfigUpdate(BaseModel):
    key: str
    value: str


class UserCreateRequest(BaseModel):
    address: str
    username: Optional[str] = None


@router.post("/config")
async def update_config(
    payload: ConfigUpdate,
    request: Request,
    admin_user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    key = payload.key
    value = payload.value
    before_value = {"key": key, "value": ADMIN_CONFIG.get(key)}
    ADMIN_CONFIG[key] = value
    after_value = {"key": key, "value": value}

    # Log to AuditLog
    log_entry = AuditLog(
        action="update_config",
        actor=admin_user.get("address"),
        target=f"config:{key}",
        before_value=before_value,
        after_value=after_value,
        timestamp=datetime.utcnow(),
        ip=request.client.host if request.client else None
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return {"status": "success", "config": ADMIN_CONFIG}


@router.post("/users")
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    admin_user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    # Check if user exists
    existing_user = db.query(User).filter(User.address == payload.address).first()
    if existing_user:
        before_val = {"id": existing_user.id, "address": existing_user.address, "username": existing_user.username}
        existing_user.username = payload.username
        db.commit()
        db.refresh(existing_user)
        after_val = {"id": existing_user.id, "address": existing_user.address, "username": existing_user.username}
        action = "update_user"
    else:
        before_val = None
        new_user = User(
            address=payload.address,
            username=payload.username,
            created_at=datetime.utcnow()
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        after_val = {"id": new_user.id, "address": new_user.address, "username": new_user.username}
        action = "create_user"

    # Log to AuditLog
    log_entry = AuditLog(
        action=action,
        actor=admin_user.get("address"),
        target=f"user:{payload.address}",
        before_value=before_val,
        after_value=after_val,
        timestamp=datetime.utcnow(),
        ip=request.client.host if request.client else None
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return {"status": "success", "user": after_val}


@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin_user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
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
    
    # Format logs output
    formatted_logs = []
    for log in logs:
        formatted_logs.append({
            "id": log.id,
            "action": log.action,
            "actor": log.actor,
            "target": log.target,
            "before_value": log.before_value,
            "after_value": log.after_value,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "ip": log.ip
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": formatted_logs
    }
