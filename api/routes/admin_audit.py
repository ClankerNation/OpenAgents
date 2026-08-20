"""
@fix-author rafaio1
@date 2026-08-20T00:00:00Z
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

"""Admin audit log endpoints for accountability and compliance."""

import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])

# In-memory immutable audit log store (would be append-only DB in production)
_audit_log: list[dict] = []


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor: str
    target: str
    before_values: Optional[dict] = None
    after_values: Optional[dict] = None
    timestamp: str
    ip_address: str


def record_audit(
    action: str,
    actor: str,
    target: str,
    before_values: dict = None,
    after_values: dict = None,
    ip_address: str = "unknown",
) -> dict:
    """Record an immutable audit log entry. No delete or update allowed."""
    entry = {
        "id": len(_audit_log) + 1,
        "action": action,
        "actor": actor,
        "target": target,
        "before_values": before_values,
        "after_values": after_values,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_address": ip_address,
    }
    _audit_log.append(entry)
    return entry


@router.get("/audit-log", response_model=list[AuditLogEntry])
async def get_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Query audit logs with filtering. Records are immutable — no POST/PUT/DELETE."""
    results = list(_audit_log)

    if actor:
        results = [r for r in results if r["actor"] == actor]
    if action:
        results = [r for r in results if r["action"] == action]
    if start_date:
        results = [r for r in results if r["timestamp"] >= start_date]
    if end_date:
        results = [r for r in results if r["timestamp"] <= end_date]

    # Sort by timestamp descending (most recent first)
    results.sort(key=lambda x: x["timestamp"], reverse=True)

    return results[offset : offset + limit]
