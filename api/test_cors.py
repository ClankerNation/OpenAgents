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
from fastapi.testclient import TestClient

class TestCORSConfiguration(unittest.TestCase):
    def test_cors_headers_with_allowed_origins(self):
        os.environ["ALLOWED_ORIGINS"] = "http://example.com,https://app.openagents.com"
        os.environ["ENV"] = "production"
        
        # Import main locally so it registers middleware with these env settings
        import importlib
        import api.main
        importlib.reload(api.main)
        
        client = TestClient(api.main.app)
        
        # Test cross-origin GET request
        headers = {"Origin": "http://example.com"}
        res = client.get("/health", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://example.com")
        self.assertEqual(res.headers.get("access-control-allow-credentials"), "true")

        # Test preflight OPTIONS request
        preflight_headers = {
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Requested-With",
        }
        res_opts = client.options("/health", headers=preflight_headers)
        self.assertEqual(res_opts.status_code, 200)
        self.assertEqual(res_opts.headers.get("access-control-allow-origin"), "http://example.com")
        self.assertEqual(res_opts.headers.get("access-control-allow-methods"), "GET, POST, PUT, DELETE, OPTIONS")

    def test_cors_restrictive_origins_by_default(self):
        # Default empty ALLOWED_ORIGINS in production
        if "ALLOWED_ORIGINS" in os.environ:
            del os.environ["ALLOWED_ORIGINS"]
        os.environ["ENV"] = "production"
        
        import importlib
        import api.main
        importlib.reload(api.main)
        
        client = TestClient(api.main.app)
        res = client.get("/health", headers={"Origin": "http://malicioussite.com"})
        self.assertIsNone(res.headers.get("access-control-allow-origin"))

    def test_cors_wildcard_allowed_in_dev_only(self):
        # Test wildcard in development
        os.environ["ALLOWED_ORIGINS"] = "*"
        os.environ["ENV"] = "development"
        
        import importlib
        import api.main
        importlib.reload(api.main)
        
        client = TestClient(api.main.app)
        res = client.get("/health", headers={"Origin": "http://anydomain.com"})
        self.assertEqual(res.headers.get("access-control-allow-origin"), "*")
        # In dev with wildcard, allow_credentials should be False (or absent) to avoid starlette runtime error
        self.assertNotEqual(res.headers.get("access-control-allow-credentials"), "true")

        # Test wildcard rejected in production
        os.environ["ALLOWED_ORIGINS"] = "*"
        os.environ["ENV"] = "production"
        
        importlib.reload(api.main)
        client_prod = TestClient(api.main.app)
        res_prod = client_prod.get("/health", headers={"Origin": "http://anydomain.com"})
        self.assertIsNone(res_prod.headers.get("access-control-allow-origin"))
