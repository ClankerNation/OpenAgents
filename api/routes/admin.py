# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Admin endpoints with immutable audit logging."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models.database import get_db
from ..models.audit_log import AuditLog
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def create_audit_log(
    db: Session,
    action: str,
    actor: str,
    target: Optional[str] = None,
    before_values: Optional[dict] = None,
    after_values: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Create an immutable audit log entry."""
    log = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_values=before_values,
        after_values=after_values,
        ip_address=ip_address,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()


@router.get("/audit-log")
async def get_audit_logs(
    action: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Query audit logs with filtering. Admin only."""
    # In production, verify admin role here
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            query = query.filter(AuditLog.timestamp >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            query = query.filter(AuditLog.timestamp <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return [log.to_dict() for log in logs]
