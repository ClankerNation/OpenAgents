"""Audit logging middleware for tracking admin actions."""

from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            body = await request.body()
            from ..models.database import AuditLog, SessionLocal
            db = SessionLocal()
            try:
                log_entry = AuditLog(
                    action=f"{request.method} {request.url.path}",
                    actor=getattr(request.state, "user", {}).get("address", "unknown"),
                    after_values={"body_preview": body.decode("utf-8", errors="replace")[:500]},
                    ip_address=request.client.host if request.client else None,
                    timestamp=datetime.utcnow(),
                )
                db.add(log_entry)
                db.commit()
            finally:
                db.close()
        response = await call_next(request)
        return response
