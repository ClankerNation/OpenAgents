"""
Admin audit log endpoints.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from api.models.database import get_db
from api.middleware.auth import get_current_user, require_role
from api.audit import AuditLogger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def get_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    """Query audit logs with pagination and filtering. Admin only."""
    logs, total = AuditLogger.query_logs(
        db=db,
        actor=actor,
        action=action,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "actor": log.actor,
                "actor_address": log.actor_address,
                "target": log.target,
                "before": log.before_values,
                "after": log.after_values,
                "ip_address": log.ip_address,
                "request_id": log.request_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }
