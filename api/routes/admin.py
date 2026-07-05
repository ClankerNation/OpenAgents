@generated-by: opencode
@platform: OpenCode (opencode.ai)
@timestamp: 2026-07-05T00:00:00+05:30
@session: This file was modified as part of the OpenAgents bounty program. All startup configuration and instructions are documented per project convention.
"

"""Admin routes for OpenAgents platform."""

from fastapi import APIRouter, Depends, Query
from typing import Any, Dict, Optional

from ..middleware.audit import log_action, get_audit_logs, clear_audit_logs
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-log")
async def list_audit_logs(limit: int = Query(100, le=1000)):
    return {"entries": get_audit_logs(limit)}


@router.delete("/audit-log")
async def delete_audit_logs(user=Depends(get_current_user)):
    log_action(
        actor=user.get("address"),
        action="clear_audit_logs",
        target="audit:log",
    )
    clear_audit_logs()
    return {"cleared": True}