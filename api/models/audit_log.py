# @fix-author rafaio1
# @date 2026-08-25T06:25:00Z
# @runtime linux x64 /tmp/openagents_issue_192 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for Admin Audit Log (Issue #192)
"""AuditLog model for immutable tracking of all admin actions."""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from .database import Base


class AuditLog(Base):
    """Immutable audit record for admin actions. No update or delete allowed."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(128), nullable=False, index=True)
    actor = Column(String(128), nullable=False, index=True)
    target = Column(String(256), nullable=True)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', actor='{self.actor}')>"
