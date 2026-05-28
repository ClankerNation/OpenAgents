"""Admin audit log endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor_id: str
    target_type: Optional[str]
    target_id: Optional[str]
    before_value: Optional[dict]
    after_value: Optional[dict]
    ip_address: Optional[str]
    timestamp: datetime

    model_config = {"from_attributes": True}


def record_audit(
    db,
    action: str,
    actor_id: str,
    target_type: str = None,
    target_id: str = None,
    before_value: dict = None,
    after_value: dict = None,
    ip_address: str = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        before_value=before_value,
        after_value=after_value,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    return entry


@router.get("/audit-log", response_model=list[AuditLogEntry])
async def get_audit_log(
    actor: Optional[str] = Query(None, description="Filter by actor ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    query = db.query(AuditLog)

    if actor:
        query = query.filter(AuditLog.actor_id == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()


@router.get("/audit-log/{log_id}", response_model=AuditLogEntry)
async def get_audit_log_entry(
    log_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    entry = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return entry
