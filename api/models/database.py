# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:32:03+07:00

"""SQLAlchemy models and database session management."""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, JSON,
    ForeignKey, DateTime, Enum as SAEnum, event
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
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(255), nullable=False)
    actor = Column(String(255), nullable=True)
    target = Column(String(255), nullable=True)
    before_value = Column(JSON, nullable=True)
    after_value = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip = Column(String(45), nullable=True)


@event.listens_for(AuditLog, "before_update")
def prevent_audit_log_update(mapper, connection, target):
    raise ValueError("AuditLog records are immutable and cannot be updated.")


@event.listens_for(AuditLog, "before_delete")
def prevent_audit_log_delete(mapper, connection, target):
    raise ValueError("AuditLog records are immutable and cannot be deleted.")


def init_db():
    Base.metadata.create_all(bind=engine)
