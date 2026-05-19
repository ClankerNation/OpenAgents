# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
#
# Agent:       myPM+ (The.PM / Gritt) - NLA Proto-ASI Agent
# Platform:    Hermes Agent (Linux)
# Model:       deepseek-v4-pro
# Timestamp:   2026-05-19T14:50:00Z
#
# Environment:
#   OS:        Linux (x86_64)
#   Arch:      x86_64
#   Home:      /root
#   Workdir:   /tmp/OpenAgents-review
#   Shell:     /bin/bash
#
# Operating Instructions (VERBATIM - session initialization context):
#
# NLA biosecure agent fleet, yellow-themed terminal agent. Policy 7: GAP-first
# code access via nla-codebase-parser :8091. Policy 9: Firecracker Browser
# Harness mandatory for all browser operations. Policy 10: AgentStream memvid+
# memory via :8408. Writing conventions: zero em-dashes (U+2014/U+2013), zero
# double-hyphen word separators, zero Oxford commas. Text brightness minimum
# #F0F0F0. Services: PAD Transform :3100, gapc :8405, GAP Runtime :8089,
# LatticeWiki :8400, Gitea :3003. All agent output English only. PAD mandatory
# for code operations. Deployment to tasty.newlisbon.agency or
# taskstar.newlisbon.agency only. Seven-layer PAD operational.
# ============================================================================

"""SQLAlchemy models and database session management.

Issue #37: Added indexes on high-traffic columns, cascade deletes,
and timezone-aware timestamps.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, JSON,
    ForeignKey, DateTime, Enum as SAEnum,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openagents.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _utcnow():
    """Return current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(42), unique=True, nullable=False, index=True)
    username = Column(String(64), unique=True, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    agents = relationship(
        "Agent", back_populates="owner", cascade="all, delete-orphan"
    )


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    model_type = Column(String(32), default="gpt-4")
    config = Column(JSON, default=dict)
    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, default=_utcnow)

    owner = relationship("User", back_populates="agents")
    tasks = relationship(
        "Task", back_populates="agent", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    reward_amount = Column(Float, nullable=False)
    status = Column(
        String(32), default="open", index=True,
    )
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)

    agent = relationship("Agent", back_populates="tasks")
    payments = relationship(
        "Payment", back_populates="task", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_address = Column(String(42), nullable=False, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    token_address = Column(
        String(42), default="0x0000000000000000000000000000000000000000"
    )
    status = Column(String(32), default="pending", index=True)
    created_at = Column(DateTime, default=_utcnow)
    claimed_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="payments")


def init_db():
    Base.metadata.create_all(bind=engine)
