"""SQLAlchemy models and database session management.

@contributor Codex Agent xyjk0511
@platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
@runtime Windows PowerShell, working directory F:/jiedan/OpenAgents-bounty-run
@date 2026-05-31T00:00:00-07:00
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


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, nullable=False, index=True)
    target_url = Column(String(2048), nullable=False)
    secret = Column(String(256), nullable=False)
    event_types = Column(JSON, default=list)
    active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    deliveries = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("webhook_subscriptions.id"), nullable=False)
    task_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, default=dict)
    status = Column(String(32), default="pending")
    attempts = Column(Integer, default=0)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    subscription = relationship("WebhookSubscription", back_populates="deliveries")


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


def init_db():
    Base.metadata.create_all(bind=engine)
