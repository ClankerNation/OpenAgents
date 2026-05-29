# ==============================================================================
# VERBATIM AGENT CONTEXT INSTRUCTIONS & ENVIRONMENT DETAILS
# OS: macOS
# CPU Architecture: Apple M1 (Mac Mini)
# Home Path: /Users/macminim1
# Working Path: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# Shell: zsh
# Agent Identity: Antigravity (Advanced Agentic Coding AI Assistant by Google DeepMind)
# ==============================================================================

import os
import time
import unittest
import jwt
from fastapi.testclient import TestClient
from api.middleware.ratelimit import _request_counts

# Set JWT secret for token encoding/decoding in tests
os.environ["JWT_SECRET"] = "test-secret-key-123"

class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        # Clear the global rate limit store before each test
        _request_counts.clear()

        # Import main locally to register middleware
        import importlib
        import api.main
        importlib.reload(api.main)
        self.client = TestClient(api.main.app)

    def test_anonymous_rate_limiting_headers(self):
        # Send a request anonymously
        res = self.client.get("/agents")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-limit"), "60")
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "59")
        self.assertTrue("x-ratelimit-reset" in res.headers)

    def test_anonymous_rate_limit_exceeded(self):
        # Mock that 59 requests were already made for the anonymous IP
        client_ip = "testclient"
        _request_counts[f"anon_{client_ip}"] = (59, time.time())
        
        # 60th request should succeed and leave 0 remaining
        res = self.client.get("/agents", headers={"X-Forwarded-For": client_ip})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "0")
        
        # 61st request should be rate limited (429)
        res_limited = self.client.get("/agents", headers={"X-Forwarded-For": client_ip})
        self.assertEqual(res_limited.status_code, 429)
        self.assertEqual(res_limited.headers.get("x-ratelimit-limit"), "60")
        self.assertEqual(res_limited.headers.get("x-ratelimit-remaining"), "0")
        self.assertTrue(int(res_limited.headers.get("retry-after")) > 0)
        self.assertTrue("retry_after" in res_limited.json())

    def test_authenticated_api_key_limits(self):
        # Test standard authenticated API Key (limit = 300)
        api_key = "standard-key-123"
        res = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-limit"), "300")
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "299")

        # Mock standard API key near limit (299 requests made)
        _request_counts[f"auth_key_{api_key}"] = (299, time.time())
        res_last = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res_last.status_code, 200)
        self.assertEqual(res_last.headers.get("x-ratelimit-remaining"), "0")

        # Next request gets rate limited
        res_limited = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res_limited.status_code, 429)

    def test_premium_api_key_limits(self):
        # Test premium API Key (limit = 1000)
        api_key = "premium-key-123"
        res = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-limit"), "1000")
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "999")

        # Mock premium API key near limit (999 requests made)
        _request_counts[f"premium_key_{api_key}"] = (999, time.time())
        res_last = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res_last.status_code, 200)
        self.assertEqual(res_last.headers.get("x-ratelimit-remaining"), "0")

        # Next request gets rate limited
        res_limited = self.client.get("/agents", headers={"X-API-Key": api_key})
        self.assertEqual(res_limited.status_code, 429)

    def test_authenticated_token_limits(self):
        # Standard token limit = 300
        payload = {"sub": "user123", "address": "0x123", "roles": ["user"], "type": "access"}
        token = jwt.encode(payload, "test-secret-key-123", algorithm="HS256")
        
        res = self.client.get("/agents", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-limit"), "300")
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "299")

    def test_premium_token_limits(self):
        # Premium token limit = 1000
        payload = {"sub": "premiumuser", "address": "0x456", "roles": ["premium"], "type": "access"}
        token = jwt.encode(payload, "test-secret-key-123", algorithm="HS256")
        
        res = self.client.get("/agents", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-ratelimit-limit"), "1000")
        self.assertEqual(res.headers.get("x-ratelimit-remaining"), "999")
