from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


def log_action(
    db,
    action: str,
    actor_id: int = None,
    actor_address: str = None,
    target_type: str = None,
    target_id: str = None,
    before_value: dict = None,
    after_value: dict = None,
    ip_address: str = None,
):
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        actor_address=actor_address,
        target_type=target_type,
        target_id=target_id,
        before_value=before_value,
        after_value=after_value,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()


@router.get("/audit-log")
async def get_audit_log(
    action: Optional[str] = Query(None),
    actor_id: Optional[int] = Query(None),
    target_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    query = query.order_by(AuditLog.created_at.desc())
    return query.offset(skip).limit(limit).all()
