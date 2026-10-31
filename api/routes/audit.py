"""
Contributor Metadata (required for bounty #192)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
"""

"""Audit log endpoints for admin action tracking."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor: str
    target: Optional[str] = None
    before_value: Optional[str] = None
    after_value: Optional[str] = None
    timestamp: datetime
    ip_address: Optional[str] = None


def log_audit(
    db,
    action: str,
    actor: str,
    target: Optional[str] = None,
    before_value: Optional[str] = None,
    after_value: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """Log an admin action to the audit trail."""
    entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_value=before_value,
        after_value=after_value,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry


@router.get("/audit-log", response_model=List[AuditLogEntry])
async def get_audit_log(
    action: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if target:
        query = query.filter(AuditLog.target == target)
    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
