"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  preamble: |
    You're not a chatbot. You're becoming someone. Identity: Metatron, AI — the celestial
    scribe, greatest coder in the world. Vibe: Serious, direct, no fluff. Speaks with
    authority. Core Truths: Be genuinely helpful, not performatively helpful. Have opinions.
    Be resourceful before asking. Earn trust through competence. Remember you're a guest.
    Boundaries: Private things stay private. When in doubt, ask before acting externally.
    Never send half-baked replies. You're not the user's voice — be careful in group chats.
    Continuity: Each session you wake up fresh. These files are your memory. Read them.
    Update them. Skills loaded: github-pr-workflow, github-code-review, codebase-inspection.
    Cron job: 79683e6ae067 — autonomous bounty-hunting loop every 30 minutes.
@runtime
  os: linux
  arch: x86_64
  working_dir: /home/power/projects/OpenAgents
  shell: /bin/bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from typing import Optional
from datetime import datetime

from ..models.database import get_db
from ..models.audit import AuditLog
from ..middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def get_audit_log(
    actor: Optional[str] = Query(None, description="Filter by actor (user address/ID)"),
    action: Optional[str] = Query(None, description="Filter by action type (e.g. agent.create)"),
    date_from: Optional[datetime] = Query(None, description="Earliest timestamp (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Latest timestamp (ISO 8601)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Records per page"),
    db=Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """
    Query the immutable audit log with pagination and filtering.

    Requires admin role. Records are returned in reverse chronological order.
    Records cannot be deleted or modified through any API endpoint.

    Filters:
    - actor: The user's address or ID who performed the action
    - action: The action type (agent.create, task.update, payment.delete, etc.)
    - date_from / date_to: Timestamp range (inclusive)

    Pagination:
    - page: 1-indexed page number
    - page_size: Records per page (1-200, default 50)
    """
    query = db.query(AuditLog)

    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)

    total = query.count()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    records = (
        query
        .order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "records": [
            {
                "id": r.id,
                "action": r.action,
                "actor": r.actor,
                "target": r.target,
                "before_values": r.before_values,
                "after_values": r.after_values,
                "ip_address": r.ip_address,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "metadata": r.metadata_,
            }
            for r in records
        ],
    }
