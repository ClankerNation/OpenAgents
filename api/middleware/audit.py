# @generated-by
# Name: elevasyncsolutions-jpg
# Timestamp: 2026-07-14T21:46:00Z
# Startup configuration: Bounty agent for ClankerNation OpenAgents. Adding audit log for admin actions. Runtime: darwin/arm64
"""Audit logging middleware for tracking admin actions."""

import json
import uuid
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

audit_log: list[dict] = []

class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            body = await request.body()
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "user": getattr(request.state, "user", {}).get("id", "anonymous"),
                "request_id": getattr(request.state, "request_id", ""),
                "body_preview": body[:500].decode("utf-8", errors="replace") if body else "",
            }
            audit_log.append(entry)
        return await call_next(request)

def get_audit_log(limit: int = 100) -> list[dict]:
    return list(reversed(audit_log))[:limit]

def get_audit_log_by_user(user_id: str, limit: int = 50) -> list[dict]:
    return [e for e in reversed(audit_log) if e["user"] == user_id][:limit]

def get_audit_log_by_action(method: str, path: str = None, limit: int = 50) -> list[dict]:
    results = [e for e in reversed(audit_log) if e["method"] == method]
    if path:
        results = [e for e in results if path in e["path"]]
    return results[:limit]
