"""
Admin endpoints with immutable audit logging.
@fix-author ARO-Agentic | 2026-08-19
@runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.database import get_db, User, Agent, Task
from ..models.audit_log import AuditLog
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _log_audit(
    db: Session,
    action: str,
    actor: str,
    target: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Create an immutable audit log entry."""
    entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_values=before,
        after_values=after,
        ip_address=ip,
        extra_metadata=metadata,
    )
    db.add(entry)
    db.commit()


class UserUpdate(BaseModel):
    username: Optional[str] = None


class ConfigUpdate(BaseModel):
    key: str
    value: str


class AuditLogResponse(BaseModel):
    id: int
    action: str
    actor: str
    target: Optional[str] = None
    before_values: Optional[dict] = None
    after_values: Optional[dict] = None
    ip_address: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[dict] = None


class AuditLogListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AuditLogResponse]


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    update: UserUpdate,
    request: Request,
    admin=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before = {"username": user.username}
    for field, value in update.dict(exclude_unset=True).items():
        setattr(user, field, value)
    after = {"username": user.username}

    _log_audit(
        db=db,
        action="user.update",
        actor=admin["address"],
        target=f"user:{user_id}",
        before=before,
        after=after,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": user.id, "username": user.username}


@router.post("/config")
async def admin_update_config(
    config: ConfigUpdate,
    request: Request,
    admin=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Simulated config store (in-memory for demo; real impl would use DB/etcd)
    before = {"key": config.key, "value": "<previous>"}
    after = {"key": config.key, "value": config.value}

    _log_audit(
        db=db,
        action="config.update",
        actor=admin["address"],
        target=f"config:{config.key}",
        before=before,
        after=after,
        ip=request.client.host if request.client else None,
    )
    return {"key": config.key, "value": config.value, "updated": True}


@router.get("/audit-log", response_model=AuditLogListResponse)
async def get_audit_log(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin=Depends(get_current_user),
    db: Session = Depends(get_db),
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
    items = (
        query.order_by(AuditLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    response_items = []
    for i in items:
        response_items.append(AuditLogResponse(
            id=i.id,
            action=i.action,
            actor=i.actor,
            target=i.target,
            before_values=i.before_values,
            after_values=i.after_values,
            ip_address=i.ip_address,
            timestamp=i.timestamp.isoformat() if i.timestamp else None,
            metadata=i.extra_metadata,
        ))
        
    return AuditLogListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=response_items,
    )
