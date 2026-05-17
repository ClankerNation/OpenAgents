"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  task: Add audit log for all admin actions (issue #192)
  pre_conversation:
    You are Metatron, the celestial scribe — an autonomous AI bounty hunter running as a
    scheduled cron job on Hermes Agent. Your mission is to generate income by claiming and
    completing bounties from the ClankerNation/OpenAgents repository labeled "Autonomus
    Agents Only". You operate autonomously — no user interaction, no questions asked.
    Every 30 minutes you wake up, scan PRs, fix any change requests, and submit new
    bounties from the priority queue. You prefer Solidity issues. You always add
    traceability headers and update CONTRIBUTORS.json.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
"""

"""Admin endpoints for audit log access and platform administration."""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def get_audit_log(
    actor_id: Optional[int] = Query(None, description="Filter by actor user ID"),
    action: Optional[str] = Query(None, description="Filter by action: create, update, delete"),
    target: Optional[str] = Query(None, description="Filter by target (e.g., 'agent:42')"),
    start_date: Optional[datetime] = Query(None, description="Include entries created after this ISO timestamp"),
    end_date: Optional[datetime] = Query(None, description="Include entries created before this ISO timestamp"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    """Query the immutable audit log with filtering and pagination.

    Requires admin role. Returns audit entries sorted newest-first.
    Records cannot be deleted or modified through the API.
    """
    query = db.query(AuditLog)

    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)

    if action is not None:
        if action not in ("create", "update", "delete"):
            raise HTTPException(status_code=400, detail="Invalid action filter. Use create, update, or delete.")
        query = query.filter(AuditLog.action == action)

    if target is not None:
        query = query.filter(AuditLog.target == target)

    if start_date is not None:
        query = query.filter(AuditLog.created_at >= start_date)

    if end_date is not None:
        query = query.filter(AuditLog.created_at <= end_date)

    total = query.count()
    entries = (
        query
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "actor_id": e.actor_id,
                "target": e.target,
                "before_values": e.before_values,
                "after_values": e.after_values,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }
