"""Admin endpoints with audit logging.

Agent Identity: OpenAgents-AuditLog-Fixer
Instructions: You are a senior open-source contributor fixing a GitHub issue for a bounty. Make the smallest correct change that follows the project's style. Never fabricate APIs. Respond with ONLY a JSON object.
Environment: Linux x86_64, /home/agent, /home/agent/OpenAgents, bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from api.models.database import get_db, AuditLog
from api.middleware.auth import require_role
import json

router = APIRouter(prefix="/admin", tags=["admin"])


def _log_audit(
    db: Session,
    action: str,
    actor: str,
    target: str,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Create an immutable audit log entry."""
    audit_entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_value=before_value,
        after_value=after_value,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    )
    db.add(audit_entry)
    db.commit()


@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """Query audit logs with filtering and pagination.
    
    Filters:
    - actor: ethereum address of action performer
    - action: type of admin action (e.g., 'user_update', 'parameter_change')
    - start_date: earliest timestamp (ISO format)
    - end_date: latest timestamp (ISO format)
    """
    query = db.query(AuditLog)
    
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "actor": log.actor,
                "target": log.target,
                "before": log.before_value,
                "after": log.after_value,
                "timestamp": log.timestamp.isoformat(),
                "ip": log.ip_address,
            }
            for log in logs
        ],
    }
