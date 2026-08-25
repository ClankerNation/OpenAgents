"""Audit logging middleware for admin actions."""

import logging
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

# @fix-author rafaio1
# @date 2026-08-25T00:00:00Z
# @runtime linux x64 /tmp/openagents_issue_192 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

logger = logging.getLogger("admin_audit")

# Endpoints that require audit logging when accessed by admins
ADMIN_ENDPOINTS = {
    "/agents/reputation",
    "/payments/admin",
    "/tasks/admin",
    "/config",
    "/admin",
}


class AdminAuditMiddleware(BaseHTTPMiddleware):
    """Logs all admin actions with user context and request details."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only log state-changing methods on sensitive endpoints
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            is_admin_endpoint = any(path.startswith(ep) for ep in ADMIN_ENDPOINTS)

            # Check if user has admin role from request state (set by auth middleware)
            user = getattr(request.state, "user", None)
            is_admin = user and "admin" in user.get("roles", [])

            if is_admin_endpoint or is_admin:
                audit_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "method": request.method,
                    "path": path,
                    "user_id": user.get("id") if user else "anonymous",
                    "user_address": user.get("address") if user else None,
                    "status_code": response.status_code,
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                }
                logger.info("ADMIN_ACTION", extra=audit_entry)

        return response
