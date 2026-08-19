"""AuditLog model for tracking admin actions immutably."""

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from .database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    actor = Column(String(256), nullable=False, index=True)
    target = Column(String(256), nullable=True)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    extra_metadata = Column("metadata", JSON, nullable=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', actor='{self.actor}')>"
