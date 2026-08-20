# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Admin endpoints with immutable audit logging."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, AuditLog, User
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _log_audit(
    db,
    action: str,
    actor: str,
    target: str | None = None,
    before_values: dict | None = None,
    after_values: dict | None = None,
    ip_address: str | None = None,
):
    """Create an immutable audit log entry."""
    entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_values=before_values,
        after_values=after_values,
        ip_address=ip_address,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    logger.info(
        "Audit: action=%s actor=%s target=%s", action, actor, target
    )


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    address: Optional[str] = None


@router.get("/audit-log")
async def get_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Query audit logs with filtering. Records are immutable."""
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
    logs = (
        query.order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": l.id,
                "action": l.action,
                "actor": l.actor,
                "target": l.target,
                "before_values": l.before_values,
                "after_values": l.after_values,
                "ip_address": l.ip_address,
                "timestamp": l.timestamp.isoformat(),
            }
            for l in logs
        ],
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    update: UpdateUserRequest,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Update user details with audit trail."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    before = {"username": target_user.username, "address": target_user.address}

    if update.username is not None:
        target_user.username = update.username
    if update.address is not None:
        target_user.address = update.address

    after = {"username": target_user.username, "address": target_user.address}

    _log_audit(
        db,
        action="UPDATE_USER",
        actor=user["address"],
        target=str(user_id),
        before_values=before,
        after_values=after,
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"user_id": user_id, "updated": after}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a user with audit trail."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    before = {"username": target_user.username, "address": target_user.address}

    _log_audit(
        db,
        action="DELETE_USER",
        actor=user["address"],
        target=str(user_id),
        before_values=before,
        after_values=None,
        ip_address=request.client.host if request.client else None,
    )

    db.delete(target_user)
    db.commit()
    return {"deleted": True, "user_id": user_id}
