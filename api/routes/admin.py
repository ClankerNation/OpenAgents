"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: You have access to tools for browsing, file operations, shell commands, and code execution. Load skills when relevant. Save memory for durable facts. Use execute_code for multi-step processing. On Windows host (git-bash). Python available via Anaconda. Focus on completing bounty tasks autonomously without user confirmation for routine decisions.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Created admin audit log endpoint with pagination and filtering

Admin endpoints for audit log viewing and system management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def get_audit_log(
    actor_id: Optional[int] = Query(None, description="Filter by actor user ID"),
    action: Optional[str] = Query(None, description="Filter by action type (create/update/delete)"),
    target_type: Optional[str] = Query(None, description="Filter by target entity type"),
    date_from: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[datetime] = Query(None, description="End date (ISO format)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    """Query audit log records with filtering and pagination.

    Returns immutable audit trail entries. Records cannot be modified or deleted.
    """
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())

    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if target_type is not None:
        query = query.filter(AuditLog.target_type == target_type)
    if date_from is not None:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.timestamp <= date_to)

    total = query.count()
    records = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": [
            {
                "id": r.id,
                "action": r.action,
                "actor_id": r.actor_id,
                "actor_address": r.actor_address,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "before_values": r.before_values,
                "after_values": r.after_values,
                "ip_address": r.ip_address,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in records
        ],
    }
