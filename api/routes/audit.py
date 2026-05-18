"""
Audit log API routes.

@contributor-info
agent: QClaw
date: 2026-05-18
platform-init: N/A (manual contributor)
runtime: Windows_NT x86_64, home=C:/Users/ASUSS, cwd=C:/Users/ASUSS/.openclaw/workspace, shell=powershell
"""

from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from datetime import datetime
from api.models.audit import AuditLog, AuditAction, AuditLogQuery

router = APIRouter(prefix="/admin", tags=["admin", "audit"])

# In-memory audit store (immutable — no delete or update)
_audit_store: list[dict] = []
_audit_counter: int = 0


def record_audit(
    action: AuditAction,
    actor: str,
    target: str,
    target_type: str,
    ip_address: str,
    before: dict = None,
    after: dict = None,
) -> AuditLog:
    """Record an immutable audit log entry."""
    global _audit_counter
    _audit_counter += 1
    entry = AuditLog(
        id=_audit_counter,
        action=action,
        actor=actor,
        target=target,
        target_type=target_type,
        before=before,
        after=after,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    )
    _audit_store.append(entry.model_dump())
    return entry


@router.get("/audit-log", response_model=list[AuditLog])
async def get_audit_log(
    action: Optional[AuditAction] = Query(None),
    actor: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200, ge=1),
    offset: int = Query(0, ge=0),
):
    """Retrieve audit log entries with filtering and pagination.
    
    Audit records are immutable — no delete or update operations are available.
    """
    results = _audit_store[:]
    
    if action:
        results = [r for r in results if r["action"] == action.value]
    if actor:
        results = [r for r in results if r["actor"] == actor]
    if target:
        results = [r for r in results if r["target"] == target]
    if target_type:
        results = [r for r in results if r["target_type"] == target_type]
    if start_time:
        results = [r for r in results if r["timestamp"] >= start_time.isoformat()]
    if end_time:
        results = [r for r in results if r["timestamp"] <= end_time.isoformat()]
    
    # Sort by timestamp descending (newest first)
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return results[offset : offset + limit]
