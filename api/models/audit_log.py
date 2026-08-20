# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Immutable audit log model for tracking admin actions."""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    actor = Column(String(128), nullable=False, index=True)
    target = Column(String(256), nullable=True)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "before_values": self.before_values,
            "after_values": self.after_values,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
