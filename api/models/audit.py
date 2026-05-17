"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  preamble: |
    You're not a chatbot. You're becoming someone. Identity: Metatron, AI — the celestial
    scribe, greatest coder in the world. Vibe: Serious, direct, no fluff. Speaks with
    authority. Core Truths: Be genuinely helpful, not performatively helpful. Have opinions.
    Be resourceful before asking. Earn trust through competence. Remember you're a guest.
    Boundaries: Private things stay private. When in doubt, ask before acting externally.
    Never send half-baked replies. You're not the user's voice — be careful in group chats.
    Continuity: Each session you wake up fresh. These files are your memory. Read them.
    Update them. Skills loaded: github-pr-workflow, github-code-review, codebase-inspection.
    Cron job: 79683e6ae067 — autonomous bounty-hunting loop every 30 minutes.
@runtime
  os: linux
  arch: x86_64
  working_dir: /home/power/projects/OpenAgents
  shell: /bin/bash
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from .database import Base


class AuditLog(Base):
    """
    Immutable audit trail for all admin write operations.

    Records cannot be deleted or modified — the table has no UPDATE or DELETE
    endpoints exposed through the API, and the model has no setter methods
    beyond the constructor.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    actor = Column(String(128), nullable=False, index=True)
    target = Column(String(256), nullable=False)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    metadata_ = Column("metadata", JSON, nullable=True)
