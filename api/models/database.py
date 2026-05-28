"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. You have persistent memory across sessions. Save durable facts using the memory tool: user preferences, environment details, tool quirks, and stable conventions. Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO state to memory. Skills: ai-comic-pipeline, bounty (clawwork, gitcoin), dreamina-cli, finance (tushare-pro). Host: Windows (10). User home directory: C:\Users\57629. Shell: git-bash / MSYS, NOT PowerShell or cmd.exe. Use POSIX shell syntax. You are on Weixin/WeChat. Markdown formatting is supported. Conversation started: Thursday, May 28, 2026 09:08 AM. Model: deepseek-v4-flash. Provider: deepseek. Tools: clarify, cronjob, delegate_task, execute_code, memory, patch, process, read_file, search_files, send_message, session_search, skill_manage, skill_view, skills_list, terminal, text_to_speech, todo, vision_analyze, write_file
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Added immutable audit log for all admin write operations (AuditLog model, audit middleware, GET /admin/audit-log endpoint with pagination/filtering, comprehensive tests)
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, JSON,
    ForeignKey, DateTime, Enum as SAEnum,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openagents.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(42), unique=True, nullable=False)
    username = Column(String(64), unique=True, nullable=True)
    # BUG: No index on address — wallet lookups on every auth request do full table scans
    created_at = Column(DateTime, default=datetime.utcnow)  # BUG: naive datetime, no timezone

    agents = relationship("Agent", back_populates="owner")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    model_type = Column(String(32), default="gpt-4")
    config = Column(JSON, default=dict)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # BUG: No cascade delete — deleting a user leaves orphaned agents
    owner = relationship("User", back_populates="agents")
    tasks = relationship("Task", back_populates="agent")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    reward_amount = Column(Float, nullable=False)
    status = Column(String(32), default="open")
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)

    agent = relationship("Agent", back_populates="tasks")
    payments = relationship("Payment", back_populates="task")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    from_address = Column(String(42), nullable=False)
    to_address = Column(String(42), nullable=True)
    amount = Column(Float, nullable=False)
    token_address = Column(String(42), default="0x0000000000000000000000000000000000000000")
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    claimed_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="payments")


class AuditLog(Base):
    """Immutable audit log for tracking all admin write operations."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(64), nullable=False)  # e.g. "create", "update", "delete"
    actor_id = Column(Integer, nullable=False)
    actor_address = Column(String(42), nullable=False)
    target_type = Column(String(64), nullable=False)  # e.g. "agent", "task", "payment"
    target_id = Column(Integer, nullable=True)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # NOTE: No update() or delete() methods are exposed for AuditLog.
    # SQLAlchemy will still allow raw UPDATE/DELETE — production deployment should
    # enforce immutability via DB trigger or restricted DB user permissions.


def init_db():
    Base.metadata.create_all(bind=engine)
