"""Admin endpoints with audit logging."""
from fastapi import APIRouter, Depends, Query
from ..models.database import get_db, AuditLog
from ..middleware.auth import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def get_audit_log(
    action: str = Query(None),
    actor: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
