"""
Audit log model and middleware for admin action tracking.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
@runtime OS=Linux 6.8.0-124-generic, arch=x86_64, workdir=/tmp/OpenAgents, shell=/bin/bash
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON as SAJSON
from sqlalchemy.orm import Session

from api.models.database import Base, get_db


class AuditLog(Base):
    """Immutable audit log entry for admin actions."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    actor = Column(String(128), nullable=False, index=True)
    actor_address = Column(String(42), nullable=True)
    target = Column(String(256), nullable=True)
    before_values = Column(SAJSON, nullable=True)
    after_values = Column(SAJSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AuditLogger:
    """Service for creating immutable audit log entries."""

    @staticmethod
    def log_action(
        db: Session,
        action: str,
        actor: str,
        target: str = None,
        before: Dict[str, Any] = None,
        after: Dict[str, Any] = None,
        ip_address: str = None,
        request_id: str = None,
        actor_address: str = None,
    ) -> AuditLog:
        """Create an immutable audit log entry."""
        entry = AuditLog(
            action=action,
            actor=actor,
            actor_address=actor_address,
            target=target,
            before_values=before,
            after_values=after,
            ip_address=ip_address,
            request_id=request_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @staticmethod
    def query_logs(
        db: Session,
        actor: str = None,
        action: str = None,
        date_from: datetime = None,
        date_to: datetime = None,
        skip: int = 0,
        limit: int = 50,
    ):
        """Query audit logs with filters."""
        from sqlalchemy import func
        query = db.query(AuditLog)

        if actor:
            query = query.filter(AuditLog.actor == actor)
        if action:
            query = query.filter(AuditLog.action == action)
        if date_from:
            query = query.filter(AuditLog.created_at >= date_from)
        if date_to:
            query = query.filter(AuditLog.created_at <= date_to)

        total = query.count()
        logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
        return logs, total


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically log admin write operations."""

    # Paths that are considered admin operations
    ADMIN_PATHS = ["/admin", "/agents", "/tasks", "/payments"]
    # HTTP methods that modify state
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only log write operations on admin paths
        if (request.method in self.WRITE_METHODS and
            any(request.url.path.startswith(p) for p in self.ADMIN_PATHS)):

            try:
                db = next(get_db())
                request_id = getattr(request.state, "request_id", None)
                actor = "system"
                actor_address = None

                # Try to extract user from request state (set by auth middleware)
                if hasattr(request.state, "user"):
                    user = request.state.user
                    actor = user.get("id", "unknown")
                    actor_address = user.get("address")

                AuditLogger.log_action(
                    db=db,
                    action=f"{request.method} {request.url.path}",
                    actor=str(actor),
                    actor_address=actor_address,
                    target=request.url.path,
                    ip_address=request.client.host if request.client else None,
                    request_id=request_id,
                )
            except Exception:
                pass  # Never let audit logging break the response

        return response
