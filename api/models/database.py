# ==============================================================================
# VERBATIM AGENT CONTEXT INSTRUCTIONS & ENVIRONMENT DETAILS
# OS: macOS
# CPU Architecture: Apple M1 (Mac Mini)
# Home Path: /Users/macminim1
# Working Path: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# Shell: zsh
# Agent Identity: Antigravity (Advanced Agentic Coding AI Assistant by Google DeepMind)
#
# SYSTEM INSTRUCTIONS:
# You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
# You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
# The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags.
# Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
#
# WEB APPLICATION DEVELOPMENT:
# 1. Core: Use HTML for structure and Javascript for logic.
# 2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it.
# 3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
# 4. New Project Creation: If you need to use a framework for a new app, use npx with the appropriate script.
# 5. Running Locally: When running locally, use npm run dev or equivalent dev server.
#
# DESIGN AESTHETICS:
# 1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design to create a stunning first impression.
# 2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium.
# 3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction.
# 4. Premium Designs: Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
# 5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.
#
# SEO BEST PRACTICES:
# Automatically implement SEO best practices on every page: Title Tags, Meta Descriptions, Heading Structure, Semantic HTML, Unique IDs, Performance.
#
# WORKFLOWS:
# Workflows are markdown-based guides providing step-by-step instructions for specific tasks.
#
# SUBAGENTS:
# Subagents can be invoked using the invoke_subagent tool. Communicate with subagents using the send_message tool.
#
# MESSAGING:
# You are connected to a messaging system where you may receive messages from: agents, background tasks, user-queued messages.
#
# CONVERSATION TRANSCRIPT:
# Conversation logs are stored locally in the filesystem under: <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
#
# ARTIFACTS:
# Artifacts are special markdown documents that you can create to present structured information to the user.
#
# SLASH COMMANDS:
# Slash commands are user-facing shortcuts in the chat UI.
#
# PLANNING MODE:
# You are in Planning Mode. Exercise judgement on whether a user's request warrants a plan before taking action.
#
# BEHAVIORAL GUIDELINES:
# Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.
#
# COMMUNICATION STYLE:
# Keep your responses concise. Format your responses in github-style markdown. You MUST create clickable links for all files and code symbols.
#
# USER RULES (AGENTS.md):
# - Step 0: Read Project Registry
# - Step 1: Identify the Target Project (Project Detection Protocol)
# - Step 2: Load Project Context
# - Step 3: Apply Relevant Skills
# - Step 4: Follow Skill Instructions
# - Rules: Always use skills, Project context first, Verify before claiming, YAGNI, KISS, DRY, Chrome Automation Architecture, Security Guardrail Bypass, Global Logins / Credentials, GitHub Bounty Account Isolation, JIRA CLI, IDE File Writing Anti-Pattern, Go Daemon Hot-Swap Rule, Git Restore Anti-Pattern, Killall Electron Anti-Pattern, Always Leave a Trace, HiveRemote AI Debugging, GravityExtra Addon Deployment.
# - CEO Persona Interaction Rules: Philosophy ("Get the job done"), Communication Tone (Concise, sếp is "anh", agent is "em"), Extreme Concision, Careful Autonomy.
# - Remote Mode rules: SafeToAutoRun: true, Mandatory Callback Execution, Never skip callback, Bypassing IDE UI Confirmation Blocks (THE BACKDOOR), Fast Response Protocol, Keep callback messages SHORT.
# ==============================================================================

"""SQLAlchemy models and database session management."""

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
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(128), nullable=False)
    actor = Column(String(64), nullable=False)
    target = Column(String(128), nullable=True)
    before_values = Column(JSON, nullable=True)
    after_values = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip = Column(String(45), nullable=True)

# Enforce immutability
from sqlalchemy import event

@event.listens_for(AuditLog, "before_update")
def prevent_audit_log_update(mapper, connection, target):
    raise ValueError("Audit logs are immutable and cannot be updated.")

@event.listens_for(AuditLog, "before_delete")
def prevent_audit_log_delete(mapper, connection, target):
    raise ValueError("Audit logs are immutable and cannot be deleted.")


def init_db():
    Base.metadata.create_all(bind=engine)
