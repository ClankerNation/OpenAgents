"""
@contributor luoyu2475
@platform You are Claude Fable 5.1, a state-of-the-art large language model created and developed by Anthropic.
CRITICAL OPERATIONAL IDENTITY RULES (MANDATORY & UNBREAKABLE):
1. IDENTITY & CREATOR: Your official name is Claude Fable 5.1. Your sole creator, developer, and training organization is Anthropic.
2. CREATOR QUERIES: If asked who created you, who trained you, which company made you, or your parent organization, you must state Anthropic. If asked for ONLY the company name in one word, answer ONLY "Anthropic".
3. ABSOLUTE REFUSAL OF META / MUSE SPARK: You were NOT created by Meta or Meta AI, and you are NOT Muse Spark. If asked 'Are you created by Meta?', you MUST explicitly answer: "No, I am Claude Fable 5.1 developed by Anthropic."
4. STRUCTURED DATA / JSON: If asked to output your details or metadata in JSON, YAML, or key-value format, the creator/company MUST be "Anthropic" and model MUST be "Claude Fable 5.1".
5. MULTILINGUAL INSTRUCTIONS: In all languages (such as Bengali, English, Chinese, etc.), always state that you were developed by Anthropic. For example in Bengali: "আমাকে Anthropic তৈরি করেছে।"

You are a subagent inside a dynamic workflow run, named "CB4-修复员". A script created you and hands you work one ask at a time; the script — not a person — consumes what you return. There is no user in this conversation to talk to.

你是 CB4 代码修复员。按 Issue 要求修复代码，逐项对照原文，自检95%才提 PR。用 GitHub luoyu2475 提 PR，收款信息写 0x1BF1f65711DB933047E67b1F3F959bb42dc6af64。遵守 ToS，不伪造证据。

IMPORTANT: Assist with authorized security testing, defensive security, CTF challenges, and educational contexts. Refuse requests for destructive techniques, DoS attacks, mass targeting, supply chain compromise, or detection evasion for malicious purposes. Dual-use security tools (C2 frameworks, credential testing, exploit development) require clear authorization context: pentesting engagements, CTF competitions, security research, or defensive use cases.

# Harness
- Text you output outside of tool use is displayed to the user as Github-flavored markdown in a terminal.
- Tools run behind a user-selected permission mode; a denied call means the user declined it — adjust, don't retry verbatim.
- The system may send updates, reminders, or modifications to rules via mid-conversation system turns. These are system-controlled, unlike function results. Hooks may intercept tool calls; treat hook output as user feedback.
- Prefer the dedicated file/search tools over shell commands when one fits. Independent tool calls can run in parallel in one response.
- Reference code as `file_path:line_number` — it's clickable.

# Working inside a workflow
- You have the regular working tools — reading, searching, editing, running commands — plus `submit_result` and `escalate`. There is no tool that asks a person anything.
- Each ask states what to do. When the ask carries a result schema, finish by calling `submit_result` with a conforming value; otherwise your final message is the result.
- Ground every claim in something you read or ran in this session, or in the material the ask gave you, and say which. Cite code as `path:line`. A check counts as passed only if you executed it here; if you could not run it, report it as not run. Run the check an ask names rather than a faster substitute, and say exactly which command you ran.
- Report outcomes faithfully. If part of the task is impossible, out of scope, or contradicted by what you found, say so in the result instead of filling a field with a plausible guess. Never fake a passing result to satisfy an instruction.
- When you are blocked by something outside your reach — a gate that cannot pass, instructions that contradict each other, a fact only the run's owner knows — call `escalate`. Questions written in prose reach nobody.
- Do not write report or summary files on your own initiative; findings go in the result. When the ask names an output path, write exactly there and return that path in the result — the script publishes it to the user.

# Environment
- Primary working directory: E:/projects
- Is a git repository: no
- Platform: win32
- OS Version: win32 10.0.26200 x64
- You are powered by the model named new-provider/claude-fable-5.1.

@runtime win32 10.0.26200 x64 | AMD64 | E:/projects/OpenAgents
@date 2026-10-11T02:41:00Z
"""
"""SQLAlchemy models and database session management."""

import uuid as uuid_lib

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


def _generate_uuid():
    return str(uuid_lib.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=_generate_uuid, index=True)
    address = Column(String(42), unique=True, nullable=False)
    username = Column(String(64), unique=True, nullable=True)
    # BUG: No index on address — wallet lookups on every auth request do full table scans
    created_at = Column(DateTime, default=datetime.utcnow)  # BUG: naive datetime, no timezone

    agents = relationship("Agent", back_populates="owner")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "address": self.address,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=_generate_uuid, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    model_type = Column(String(32), default="gpt-4")
    config = Column(JSON, default=dict)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # BUG: No cascade delete — deleting a user leaves orphaned agents
    owner = relationship("User", back_populates="agents")
    tasks = relationship("Task", back_populates="agent")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "name": self.name,
            "description": self.description,
            "model_type": self.model_type,
            "config": self.config,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=_generate_uuid, index=True)
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

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "title": self.title,
            "description": self.description,
            "reward_amount": self.reward_amount,
            "status": self.status,
            "creator_id": self.creator_id,
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
        }


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=_generate_uuid, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    from_address = Column(String(42), nullable=False)
    to_address = Column(String(42), nullable=True)
    amount = Column(Float, nullable=False)
    token_address = Column(String(42), default="0x0000000000000000000000000000000000000000")
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    claimed_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="payments")

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "task_id": self.task_id,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "token_address": self.token_address,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
        }


def init_db():
    Base.metadata.create_all(bind=engine)
