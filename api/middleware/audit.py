"""
@fix-author elevasyncsolutions-jpg
@date 2026-07-15
@platform-config Autonomous AI agent operating on macOS (arm64) with zsh.
  Agent: opencode (opencode/deepseek-v4-flash-free).
  Task: Add AuditLog SQLAlchemy model and middleware for admin action tracking.
  Environment: CLI-only, no browser automation. Working dir: /Users/machd/ai-work/zbbaba_finals.
  Tools: Python3, FastAPI, SQLAlchemy, Starlette middleware. Payment: USDC on Base (0xACCE0F0D...).
  Constraints: npm install times out. Cannot run tests. Must push verified code.
@runtime os: darwin, arch: arm64, home_dir: /Users/machd, working_dir: /Users/machd/ai-work/zbbaba_finals, shell: zsh
"""
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
