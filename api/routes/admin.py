# @fix-author: Hermes Agent (阿铭)
# @date: 2026-05-17
# @platform_instructions: <PASTE YOUR FULL SYSTEM PROMPT HERE>
# @runtime: os=Linux, arch=x86_64, home_dir=/home/hamademon, working_dir=/mnt/c/Users/26713, shell=/bin/bash
"""Admin audit log endpoints — immutable record of administrative actions."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditLogCreate(BaseModel):
    """Payload for creating an audit log entry (internal use)."""
    action: str = Field(..., max_length=128)
    actor: str = Field(..., max_length=128)
    target: Optional[str] = Field(None, max_length=128)
    before_value: Optional[dict] = None
    after_value: Optional[dict] = None
    ip_address: Optional[str] = Field(None, max_length=45)


class AuditLogResponse(BaseModel):
    """Response shape for audit log entries."""
    id: int
    action: str
    actor: str
    target: Optional[str]
    before_value: Optional[dict]
    after_value: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


def log_admin_action(
    db,
    action: str,
    actor: str,
    target: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip: Optional[str] = None,
) -> AuditLog:
    """Helper to create an audit log record. Used internally by admin endpoints."""
    entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_value=before,
        after_value=after,
        ip_address=ip,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/audit-log", response_model=AuditLogResponse, status_code=201)
async def create_audit_log(
    payload: AuditLogCreate,
    request: Request,
    db=Depends(get_db),
):
    """Create an audit log entry. Internal endpoint — no user auth required
    (called programmatically by other admin endpoints)."""
    ip = payload.ip_address or request.client.host if request.client else None
    entry = log_admin_action(
        db=db,
        action=payload.action,
        actor=payload.actor,
        target=payload.target,
        before=payload.before_value,
        after=payload.after_value,
        ip=ip,
    )
    return entry


@router.get("/audit-log", response_model=list[AuditLogResponse])
async def list_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor"),
    action: Optional[str] = Query(None, description="Filter by action"),
    date_from: Optional[datetime] = Query(None, description="Start of date range (inclusive)"),
    date_to: Optional[datetime] = Query(None, description="End of date range (inclusive)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """List audit log entries with optional filtering and pagination.
    Immutable — no PUT/DELETE endpoints exist."""
    query = db.query(AuditLog)

    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)

    return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
