"""Admin endpoints with immutable audit logging (Issue #192).
@fix-author rafaio1
@date 2026-08-25T02:40:00Z
@runtime linux x64 /tmp/openagents_issue_202 bash
@platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog, User
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


def _log_admin_action(
    db,
    action: str,
    actor_id: int,
    target_type: str = None,
    target_id: str = None,
    before_values: dict = None,
    after_values: dict = None,
    ip_address: str = None,
):
    """Create an immutable audit log entry."""
    log_entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        before_values=before_values,
        after_values=after_values,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    )
    db.add(log_entry)
    db.commit()


@router.get("/audit-log")
async def get_audit_log(
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    """Query audit logs with filtering. Records are immutable — no delete/update endpoints exist."""
    query = db.query(AuditLog)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
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
        "entries": [
            {
                "id": log.id,
                "action": log.action,
                "actor_id": log.actor_id,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "before_values": log.before_values,
                "after_values": log.after_values,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in logs
        ],
    }
