from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = Query(None),
    admin_id: Optional[int] = Query(None),
    resource_type: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if admin_id:
        query = query.filter(AuditLog.admin_id == admin_id)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if success is not None:
        query = query.filter(AuditLog.success == int(success))
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()


@router.get("/audit-logs/summary")
async def audit_log_summary(
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    total = db.query(AuditLog).count()
    action_counts = {}
    for row in db.query(AuditLog.action, AuditLog.id).all():
        action_counts[row.action] = action_counts.get(row.action, 0) + 1
    return {"total_actions": total, "by_action": action_counts}


@router.get("/audit-logs/{log_id}")
async def get_audit_log(
    log_id: int,
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return log
