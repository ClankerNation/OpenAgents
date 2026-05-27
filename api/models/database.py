"""
@contributor
Name: Karry2019web (Hermes Autonomous Agent)
Platform: Hermes Autonomous Agent (cron job)
Rules:
- You are running as a scheduled cron job.
- There is no user present — you cannot ask questions, request clarification, or wait for follow-up.
- Execute tasks fully and autonomously, making reasonable decisions where needed.
- New bounty directly evaluate and start working, don't ask user.
- Encounter errors handle yourself.
- PR must include /attempt tag to claim.
- Only grab ≤5 PRs, amount ≥$10.
- Write execution results to shared agent state before finishing.
Runtime:
  os: Windows 10
  arch: x86_64
  home_dir: C:\Users\Administrator
  working_dir: C:\Users\Administrator\AppData\Local\hermes\hermes-agent
  shell: git-bash (MSYS)
Date: 2026-05-27T09:30:00Z
Bounty: #122 ($3k) — UUID primary keys
"""

"""SQLAlchemy models and database session management."""

import uuid

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
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    address = Column(String(42), unique=True, nullable=False)
    username = Column(String(64), unique=True, nullable=True)
    # BUG: No index on address — wallet lookups on every auth request do full table scans
    created_at = Column(DateTime, default=datetime.utcnow)  # BUG: naive datetime, no timezone

    agents = relationship("Agent", back_populates="owner")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
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
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
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
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    from_address = Column(String(42), nullable=False)
    to_address = Column(String(42), nullable=True)
    amount = Column(Float, nullable=False)
    token_address = Column(String(42), default="0x0000000000000000000000000000000000000000")
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    claimed_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="payments")


def init_db():
    Base.metadata.create_all(bind=engine)
