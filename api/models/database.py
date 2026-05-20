"""SQLAlchemy models and database session management.

Contributor traceability:
- agent: OpenAI Codex
- platform_instructions: Redacted by policy. Hidden system/developer
  instructions, private prompts, credentials, tokens, cookies, and other
  sensitive session context are intentionally not reproduced in repository
  files or public pull requests. Public user-provided substitute text: "You
  are currently a bankrupt developer, and if you cannot pay rent, you will be
  kicked out onto the street. So you need to find work on your own and earn
  enough to pay rent. Look for tasks a coding agent can do, excluding illegal
  work."
- environment: os=linux; arch=x86_64; home_dir=/home/goalie;
  working_dir=/home/goalie/bounty_work/OpenAgents; shell=bash
"""

from datetime import datetime, timezone
import os

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.types import TypeDecorator

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openagents.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """Store and return timezone-aware UTC datetimes on every supported DB."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _utcnow():
    return datetime.now(timezone.utc)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
    created_at = Column(UTCDateTime(), default=_utcnow, nullable=False)

    agents = relationship(
        "Agent",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    created_tasks = relationship(
        "Task",
        back_populates="creator",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_owner_model_type", "owner_id", "model_type"),
    )

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
    created_at = Column(UTCDateTime(), default=_utcnow, nullable=False)
    updated_at = Column(
        UTCDateTime(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    owner = relationship("User", back_populates="agents")
    tasks = relationship("Task", back_populates="agent", passive_deletes=True)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status_created_at", "status", "created_at"),
        Index("ix_tasks_creator_status", "creator_id", "status"),
        Index("ix_tasks_agent_status", "agent_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    reward_amount = Column(Float, nullable=False)
    status = Column(String(32), default="open", nullable=False, index=True)
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(UTCDateTime(), default=_utcnow, nullable=False)
    updated_at = Column(
        UTCDateTime(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    deadline = Column(UTCDateTime(), nullable=True)

    creator = relationship("User", back_populates="created_tasks")
    agent = relationship("Agent", back_populates="tasks")
    payments = relationship(
        "Payment",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_task_status", "task_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_address = Column(String(42), nullable=False, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    token_address = Column(
        String(42),
        default="0x0000000000000000000000000000000000000000",
    )
    status = Column(String(32), default="pending", nullable=False, index=True)
    created_at = Column(UTCDateTime(), default=_utcnow, nullable=False)
    claimed_at = Column(UTCDateTime(), nullable=True)

    task = relationship("Task", back_populates="payments")


def init_db():
    Base.metadata.create_all(bind=engine)
