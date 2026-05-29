"""Admin audit log endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..middleware.auth import require_role
from ..models.database import AuditLog, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
admin_required = require_role("admin")


def create_audit_log(
    db: Session,
    *,
    action: str,
    actor: str,
    target: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip: Optional[str] = None,
) -> AuditLog:
    audit_log = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before=before,
        after=after,
        ip=ip,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log


def audit_admin_action(
    db: Session,
    request: Request,
    *,
    action: str,
    actor: str,
    target: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> AuditLog:
    client_ip = request.client.host if request.client else None
    return create_audit_log(
        db,
        action=action,
        actor=actor,
        target=target,
        before=before,
        after=after,
        ip=client_ip,
    )


@router.get("/audit-log")
async def list_audit_log(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _admin=Depends(admin_required),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if since:
        query = query.filter(AuditLog.timestamp >= since)
    if until:
        query = query.filter(AuditLog.timestamp <= until)

    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
