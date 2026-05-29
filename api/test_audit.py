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

import os
import unittest
from datetime import datetime, timedelta

# Set JWT secret for testing before importing dependencies that read it
os.environ["JWT_SECRET"] = "testsecretkeyfortestingonly12345"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.main import app
from api.models.database import Base, get_db, AuditLog, User, Agent
from api.middleware.auth import generate_login_tokens

# Test database setup with file path to avoid memory database isolation issues
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_openagents.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class TestAuditLogAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)
        if os.path.exists("test_openagents.db"):
            try:
                os.remove("test_openagents.db")
            except Exception:
                pass

    def setUp(self):
        # Clear database and recreate tables before each test
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()

        # Seed standard users
        self.admin_user_db = User(address="0xAdminAddress123", username="admin_guy")
        self.normal_user_db = User(address="0xUserAddress456", username="normal_guy")
        self.db.add(self.admin_user_db)
        self.db.add(self.normal_user_db)
        self.db.commit()
        self.db.refresh(self.admin_user_db)
        self.db.refresh(self.normal_user_db)

        # Generate tokens
        admin_tokens = generate_login_tokens(
            user_id=str(self.admin_user_db.id),
            address=self.admin_user_db.address,
            roles=["admin"]
        )
        self.admin_headers = {"Authorization": f"Bearer {admin_tokens['token']}"}

        normal_tokens = generate_login_tokens(
            user_id=str(self.normal_user_db.id),
            address=self.normal_user_db.address,
            roles=["user"]
        )
        self.normal_headers = {"Authorization": f"Bearer {normal_tokens['token']}"}

    def tearDown(self):
        self.db.close()

    def test_non_admin_cannot_access_audit_log(self):
        # Attempt without credentials should result in 401 (Missing auth header)
        res = self.client.get("/admin/audit-log")
        self.assertEqual(res.status_code, 401)

        # Attempt with normal user credentials should result in 403 (Insufficient permissions)
        res = self.client.get("/admin/audit-log", headers=self.normal_headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("required", res.json().get("detail", "").lower())

    def test_admin_write_user_creates_audit_log(self):
        # Create a user to update
        target_user = User(address="0xTargetAddress789", username="target_original")
        self.db.add(target_user)
        self.db.commit()

        # Update username via admin endpoint
        payload = {"username": "target_new_name"}
        res = self.client.post(
            f"/admin/users/{target_user.id}/username",
            json=payload,
            headers=self.admin_headers
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["username"], "target_new_name")

        # Verify audit log was created
        audit_log = self.db.query(AuditLog).filter(AuditLog.target == f"user:{target_user.id}").first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.action, "update_user_username")
        self.assertEqual(audit_log.actor, self.admin_user_db.address)
        self.assertEqual(audit_log.before_values, {"username": "target_original"})
        self.assertEqual(audit_log.after_values, {"username": "target_new_name"})

    def test_admin_write_agent_creates_audit_log(self):
        # Create an agent to update config
        target_agent = Agent(
            name="Test Agent",
            description="Bounty solving agent",
            model_type="gpt-4",
            config={"temperature": 0.5},
            owner_id=self.normal_user_db.id
        )
        self.db.add(target_agent)
        self.db.commit()

        # Update config via admin endpoint
        payload = {"config": {"temperature": 0.9, "max_tokens": 150}}
        res = self.client.post(
            f"/admin/agents/{target_agent.id}/config",
            json=payload,
            headers=self.admin_headers
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["agent"]["config"]["temperature"], 0.9)

        # Verify audit log
        audit_log = self.db.query(AuditLog).filter(AuditLog.target == f"agent:{target_agent.id}").first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.action, "update_agent_config")
        self.assertEqual(audit_log.before_values, {"config": {"temperature": 0.5}})
        self.assertEqual(audit_log.after_values, {"config": {"temperature": 0.9, "max_tokens": 150}})

    def test_query_filtering_and_pagination(self):
        # Create some direct audit logs with different actors, actions, and dates
        log1 = AuditLog(
            action="update_setting",
            actor="actor_a",
            target="system",
            before_values={},
            after_values={},
            timestamp=datetime.utcnow() - timedelta(days=5),
            ip="127.0.0.1"
        )
        log2 = AuditLog(
            action="update_setting",
            actor="actor_b",
            target="system",
            before_values={},
            after_values={},
            timestamp=datetime.utcnow() - timedelta(days=2),
            ip="127.0.0.1"
        )
        log3 = AuditLog(
            action="delete_user",
            actor="actor_a",
            target="user:99",
            before_values={},
            after_values={},
            timestamp=datetime.utcnow(),
            ip="127.0.0.1"
        )
        self.db.add_all([log1, log2, log3])
        self.db.commit()

        # Test filter by actor
        res = self.client.get("/admin/audit-log?actor=actor_a", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        logs = res.json()["logs"]
        self.assertEqual(len(logs), 2)
        actors = [l["actor"] for l in logs]
        self.assertIn("actor_a", actors)
        self.assertNotIn("actor_b", actors)

        # Test filter by action
        res = self.client.get("/admin/audit-log?action=update_setting", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        logs = res.json()["logs"]
        self.assertEqual(len(logs), 2)
        actions = [l["action"] for l in logs]
        self.assertIn("update_setting", actions)
        self.assertNotIn("delete_user", actions)

        # Test filter by date range
        start_date = (datetime.utcnow() - timedelta(days=3)).isoformat()
        res = self.client.get(f"/admin/audit-log?start_date={start_date}", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        logs = res.json()["logs"]
        self.assertEqual(len(logs), 2)

        # Test pagination (skip, limit)
        res = self.client.get("/admin/audit-log?skip=1&limit=1", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["logs"]), 1)
        self.assertEqual(res.json()["total"], 3)

    def test_audit_logs_are_immutable(self):
        log = AuditLog(
            action="update_setting",
            actor="admin_user",
            target="system",
            before_values={},
            after_values={},
            timestamp=datetime.utcnow(),
            ip="127.0.0.1"
        )
        self.db.add(log)
        self.db.commit()

        # Verify updating raises ValueError
        log.action = "malicious_hack"
        with self.assertRaises(ValueError):
            self.db.commit()
        self.db.rollback()

        # Verify deleting raises ValueError
        self.db.delete(log)
        with self.assertRaises(ValueError):
            self.db.commit()
        self.db.rollback()
