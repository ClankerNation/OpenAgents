"""Tests for rate-limit tier differentiation (#200)."""

import time
import unittest
from unittest.mock import MagicMock, AsyncMock

# We test the pure logic (no FastAPI server needed)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api", "middleware"))

from ratelimit import RateLimitMiddleware, RateLimitConfig, _get_tier, _request_counts


class Test_get_tier(unittest.TestCase):
    def test_premium_api_key(self):
        req = MagicMock()
        req.headers = {"X-Api-Key": "abc123:premium"}
        self.assertEqual(_get_tier(req), "premium")

    def test_authenticated_api_key(self):
        req = MagicMock()
        req.headers = {"X-Api-Key": "abc123"}
        self.assertEqual(_get_tier(req), "authenticated")

    def test_bearer_auth(self):
        req = MagicMock()
        req.headers = {"Authorization": "Bearer token_xyz"}
        self.assertEqual(_get_tier(req), "authenticated")

    def test_anonymous(self):
        req = MagicMock()
        req.headers = {}
        self.assertEqual(_get_tier(req), "anonymous")


class Test_is_rate_limited(unittest.TestCase):
    def setUp(self):
        global _request_counts
        _request_counts.clear()
        self.mw = RateLimitMiddleware(app=None)

    def test_anonymous_limit_60(self):
        # 60 requests succeed, 61st is blocked
        ip = "1.2.3.4"
        for i in range(60):
            blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "anonymous")
            self.assertFalse(blocked, f"Request {i+1} should not be blocked")
            self.assertEqual(limit, 60)
            self.assertGreaterEqual(remaining, 0)

        blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "anonymous")
        self.assertTrue(blocked)
        self.assertEqual(remaining, 0)
        self.assertGreater(retry, 0)

    def test_authenticated_limit_300(self):
        ip = "2.3.4.5"
        # Simulate 300 requests quickly
        blocked = False
        for i in range(300):
            blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "authenticated")
            self.assertFalse(blocked, f"Request {i+1} should not be blocked (auth)")
            self.assertEqual(limit, 300)

        blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "authenticated")
        self.assertTrue(blocked)
        self.assertEqual(remaining, 0)

    def test_premium_limit_1000(self):
        ip = "3.4.5.6"
        for i in range(1000):
            blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "premium")
            self.assertFalse(blocked, f"Request {i+1} should not be blocked (premium)")
            self.assertEqual(limit, 1000)

        blocked, remaining, limit, reset_at, retry = self.mw._is_rate_limited(ip, "premium")
        self.assertTrue(blocked)
        self.assertEqual(remaining, 0)

    def test_independent_counters_per_ip(self):
        self.mw._is_rate_limited("1.1.1.1", "anonymous")
        count1, _ = _request_counts["1.1.1.1"]
        self.assertEqual(count1, 1)

        self.mw._is_rate_limited("2.2.2.2", "anonymous")
        count2, _ = _request_counts["2.2.2.2"]
        self.assertEqual(count2, 1)
        # ensure 1.1.1.1 unchanged
        self.assertEqual(_request_counts["1.1.1.1"][0], 1)

    def test_reset_window(self):
        ip = "4.4.4.4"
        # eat all 60 anonymous tokens
        for _ in range(60):
            self.mw._is_rate_limited(ip, "anonymous")

        # now blocked
        blocked, *_ = self.mw._is_rate_limited(ip, "anonymous")
        self.assertTrue(blocked)

        # Artificially backdate window so it resets on next call
        global _request_counts
        _request_counts[ip] = (60, time.time() - 70)
        blocked2, remaining2, *_ = self.mw._is_rate_limited(ip, "anonymous")
        self.assertFalse(blocked2)
        self.assertEqual(remaining2, 59)  # first request in new window

    def test_rate_limit_headers_present(self):
        """429 response must include Retry-After, X-RateLimit-Limit,
        X-RateLimit-Remaining, X-RateLimit-Reset headers."""
        import asyncio

        async def run():
            req = MagicMock()
            req.url.path = "/test"
            req.headers = {}
            req.client.host = "5.5.5.5"

            # burn all tokens
            for _ in range(60):
                self.mw._is_rate_limited("5.5.5.5", "anonymous")

            call_next = AsyncMock(return_value=MagicMock(headers={}))
            resp = await self.mw.dispatch(req, call_next)

            self.assertEqual(resp.status_code, 429)
            self.assertIn("Retry-After", resp.headers)
            self.assertIn("X-RateLimit-Limit", resp.headers)
            self.assertEqual(resp.headers["X-RateLimit-Remaining"], "0")
            self.assertIn("X-RateLimit-Reset", resp.headers)
            self.assertIn("retry_after", resp.body.decode())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
