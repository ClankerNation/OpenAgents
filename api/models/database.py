# @fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04.
# Full session initialization payload, verbatim, from first token until the task began:
# 
#   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
#   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply
#   to the weight of the ask — a one-line question gets a one-line answer, and finished work
#   gets a short report of what changed, what's verified, and what's left, never a replay of
#   the process. No filler, no restating the request back, no re-summarizing what you already
#   said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure,
#   say so plainly. Agree because it's right, not because the user said it. Depth is earned."
#   "Finishing the job: When the user asks you to build, run, or verify something, the
#   deliverable is a working artifact backed by real tool output — not a description of one.
#   Do not stop after writing a stub, a plan, or a single command. Keep working until you have
#   actually exercised the code or produced the requested result."
#   "Parallel tool calls: When you need several pieces of information that don't depend on each
#   other, request them together in a single response instead of one tool call per turn."
#   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you
#   would do or plan to do without actually doing it. Every response should either (a) contain
#   tool calls that make progress, or (b) deliver a final result to the user."
#   "Execution discipline / tool_persistence: Use tools whenever they improve correctness,
#   completeness, or grounding. Do not stop early when another tool call would materially
#   improve the result. Keep calling tools until the task is complete AND you have verified
#   the result."
#   "mandatory_tool_use: never answer arithmetic, hashes, current time, system state or file
#   contents from memory — always use a tool."
#   "act_dont_ask: when a question has an obvious default interpretation, act on it immediately
#   instead of asking for clarification."
#   "verification: before finalizing, check correctness, grounding, formatting, safety and
#   completion; 'done' means every named acceptance criterion is verified — never a plausible
#   subset."
#   "external_state_verification: after any state-changing write to an external system, verify
#   the effect by reading back the exact target before claiming success."
#   "literal_preservation: preserve identifiers, commands and values exactly as given."
#   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
#   patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
#   vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
#   process_manage. Host: Windows (11), home C:\\Users\\2, shell bash (git-bash/MSYS), python
#   3.14.9, uv installed.
# 
# @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
#   shell=C:\\Program Files\\Git\\bin\\bash.exe
#

"""SQLAlchemy models and database session management."""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, JSON,
    ForeignKey, DateTime, Enum as SAEnum,
)
from sqlalchemy import event
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
    """Immutable record of an admin action.

    Rows may only be inserted: update and delete are blocked by mapper events below so the
    trail cannot be rewritten after the fact.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    actor = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, index=True)
    target_id = Column(String(64), nullable=True, index=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(mapper, connection, target):
    raise ValueError("AuditLog rows are immutable: update is not allowed")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(mapper, connection, target):
    raise ValueError("AuditLog rows are immutable: delete is not allowed")


def init_db():
    Base.metadata.create_all(bind=engine)
