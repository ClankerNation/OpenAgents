"""
@generated-by: hermes-agent (scotia1973-bot)
@generated-timestamp: 2026-07-03T21:50:00Z
@bounty: #174
@purpose: Comprehensive tests for the three-tier rate limiter.

Verifies:
  - Anonymous users are limited to 60 req/min
  - Authenticated users (valid JWT) are limited to 300 req/min
  - Premium users (JWT with "premium" role) are limited to 1000 req/min
  - Rate-limit headers (X-RateLimit-Limit, X-RateLimit-Remaining,
    X-RateLimit-Reset, X-RateLimit-Tier) are present on every response
  - 429 responses include Retry-After header
  - /health endpoint is not rate-limited
  - Tiers are correctly identified from the Authorization header
  - Invalid/malformed tokens fall back to anonymous tier
"""

import pytest
import time
import jwt
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitConfig,
    _get_tier,
    _request_counts,
    TIER_LIMITS,
)

# We need a minimal FastAPI app with the middleware for integration tests
# Use the existing app or build a minimal test app
from api.main import app

# Create a clean app for our rate limit tests with known config
test_app = FastAPI()
test_config = RateLimitConfig(
    anonymous_limit=60,
    authenticated_limit=300,
    premium_limit=1000,
    window_seconds=60,
)
test_app.add_middleware(RateLimitMiddleware, config=test_config)


@test_app.get("/test-endpoint")
async def test_endpoint():
    return {"status": "ok"}


@test_app.get("/health")
async def health():
    return {"status": "healthy"}


client = TestClient(test_app)

# A valid JWT secret and tokens for testing
TEST_JWT_SECRET = "test-secret-for-testing-only"
PREMIUM_JWT = jwt.encode(
    {"sub": "premium-user", "roles": ["premium"], "type": "access"},
    TEST_JWT_SECRET,
    algorithm="HS256",
)
AUTH_JWT = jwt.encode(
    {"sub": "auth-user", "roles": [], "type": "access"},
    TEST_JWT_SECRET,
    algorithm="HS256",
)
EXPIRED_JWT = jwt.encode(
    {"sub": "expired-user", "roles": [], "type": "access", "exp": 0},
    TEST_JWT_SECRET,
    algorithm="HS256",
)


class TestGetTier:
    """Unit tests for the _get_tier function."""

    def test_no_auth_header_is_anonymous(self):
        """A request without Authorization header → anonymous."""
        request = MagicMock(spec=object)
        request.headers = {}
        assert _get_tier(request) == "anonymous"

    def test_empty_auth_header_is_anonymous(self):
        """A request with empty Authorization → anonymous."""
        request = MagicMock(spec=object)
        request.headers = {"Authorization": ""}
        assert _get_tier(request) == "anonymous"

    def test_malformed_token_is_anonymous(self):
        """A request with a garbage token → anonymous."""
        request = MagicMock(spec=object)
        request.headers = {"Authorization": "Bearer this-is-not-a-valid-token"}
        assert _get_tier(request) == "anonymous"

    def test_valid_auth_token_is_authenticated(self):
        """A request with a valid JWT (no premium role) → authenticated."""
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            request = MagicMock(spec=object)
            request.headers = {"Authorization": f"Bearer {AUTH_JWT}"}
            assert _get_tier(request) == "authenticated"

    def test_premium_token_is_premium(self):
        """A request with a valid JWT containing 'premium' role → premium."""
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            request = MagicMock(spec=object)
            request.headers = {"Authorization": f"Bearer {PREMIUM_JWT}"}
            assert _get_tier(request) == "premium"

    def test_expired_token_is_anonymous(self):
        """A request with an expired JWT → anonymous."""
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            request = MagicMock(spec=object)
            request.headers = {"Authorization": f"Bearer {EXPIRED_JWT}"}
            assert _get_tier(request) == "anonymous"

    def test_no_jwt_secret_falls_to_anonymous(self):
        """If JWT_SECRET env var is not set, all requests are anonymous."""
        with patch.dict(os.environ, {}, clear=True):
            request = MagicMock(spec=object)
            request.headers = {"Authorization": f"Bearer {AUTH_JWT}"}
            assert _get_tier(request) == "anonymous"


class TestTierLimits:
    """Verify the tier limit constants."""

    def test_anonymous_limit(self):
        assert TIER_LIMITS["anonymous"]["limit"] == 60

    def test_authenticated_limit(self):
        assert TIER_LIMITS["authenticated"]["limit"] == 300

    def test_premium_limit(self):
        assert TIER_LIMITS["premium"]["limit"] == 1000


class TestRateLimitHeaders:
    """Verify rate-limit headers are present on all responses."""

    EXPECTED_HEADERS = {
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-RateLimit-Tier",
    }

    def test_anonymous_has_all_headers(self):
        """Anonymous request should have all four rate-limit headers."""
        # Clear request counts for deterministic test
        _request_counts.clear()

        resp = client.get("/test-endpoint")
        assert resp.status_code == 200
        for header in self.EXPECTED_HEADERS:
            assert header in resp.headers, f"Missing header: {header}"
        assert resp.headers["X-RateLimit-Limit"] == "60"
        assert resp.headers["X-RateLimit-Tier"] == "anonymous"

    def test_authenticated_has_all_headers(self):
        """Authenticated request should have correct headers."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            resp = client.get(
                "/test-endpoint",
                headers={"Authorization": f"Bearer {AUTH_JWT}"},
            )
        assert resp.status_code == 200
        for header in self.EXPECTED_HEADERS:
            assert header in resp.headers, f"Missing header: {header}"
        assert resp.headers["X-RateLimit-Limit"] == "300"
        assert resp.headers["X-RateLimit-Tier"] == "authenticated"

    def test_premium_has_all_headers(self):
        """Premium request should have correct headers."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            resp = client.get(
                "/test-endpoint",
                headers={"Authorization": f"Bearer {PREMIUM_JWT}"},
            )
        assert resp.status_code == 200
        for header in self.EXPECTED_HEADERS:
            assert header in resp.headers, f"Missing header: {header}"
        assert resp.headers["X-RateLimit-Limit"] == "1000"
        assert resp.headers["X-RateLimit-Tier"] == "premium"

    def test_health_endpoint_has_no_rate_limit_headers(self):
        """/health should not add rate-limit headers since it's skipped."""
        _request_counts.clear()
        resp = client.get("/health")
        assert resp.status_code == 200
        # Health endpoint is excluded from rate limiting
        for header in self.EXPECTED_HEADERS:
            assert header not in resp.headers, (
                f"Health endpoint should not have {header}"
            )


class TestRateLimitEnforcement:
    """Verify rate limits are enforced at the right thresholds."""

    def test_anonymous_exhausts_limit_returns_429(self):
        """After 60 anonymous requests, the 61st should get 429."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            # Make 60 requests (the limit for anonymous)
            for i in range(60):
                resp = client.get("/test-endpoint")
                assert resp.status_code == 200, f"Request {i+1} failed: {resp.text}"
                remaining = int(resp.headers["X-RateLimit-Remaining"])
                assert remaining == 59 - i, (
                    f"Request {i+1}: expected {59-i} remaining, got {remaining}"
                )

            # The 61st request should be rate-limited
            resp = client.get("/test-endpoint")
            assert resp.status_code == 429, f"Expected 429, got {resp.status_code}"
            body = resp.json()
            assert body["error"] == "Rate limit exceeded"
            assert "Retry-After" in resp.headers
            assert int(resp.headers["Retry-After"]) > 0
            assert resp.headers["X-RateLimit-Tier"] == "anonymous"

    def test_authenticated_higher_limit(self):
        """Authenticated users should get 300 req/min, not 60."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            # Make 70 requests — this would exceed the anonymous limit (60)
            # but should still succeed for authenticated users (limit=300)
            for i in range(70):
                resp = client.get(
                    "/test-endpoint",
                    headers={"Authorization": f"Bearer {AUTH_JWT}"},
                )
                assert resp.status_code == 200, f"Request {i+1} failed: {resp.text}"
                assert resp.headers["X-RateLimit-Tier"] == "authenticated"
                assert int(resp.headers["X-RateLimit-Limit"]) == 300

    def test_premium_highest_limit(self):
        """Premium users should get 1000 req/min."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            # Make 350 requests — exceeds authenticated (300) but under premium (1000)
            for i in range(350):
                resp = client.get(
                    "/test-endpoint",
                    headers={"Authorization": f"Bearer {PREMIUM_JWT}"},
                )
                assert resp.status_code == 200, f"Request {i+1} failed: {resp.text}"
                assert resp.headers["X-RateLimit-Tier"] == "premium"
                assert int(resp.headers["X-RateLimit-Limit"]) == 1000

    def test_anonymous_does_not_affect_authenticated_counters(self):
        """Anonymous and authenticated users should have independent counters."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            # Exhaust anonymous limit (60 requests)
            for _ in range(60):
                client.get("/test-endpoint")

            # Anonymous should now be blocked
            resp = client.get("/test-endpoint")
            assert resp.status_code == 429

            # But authenticated should still work (independent counter)
            resp = client.get(
                "/test-endpoint",
                headers={"Authorization": f"Bearer {AUTH_JWT}"},
            )
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 299

    def test_authenticated_does_not_affect_anonymous_counters(self):
        """Authenticated user's usage should not reduce anonymous limits."""
        _request_counts.clear()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}):
            # Make 200 authenticated requests
            for _ in range(200):
                client.get(
                    "/test-endpoint",
                    headers={"Authorization": f"Bearer {AUTH_JWT}"},
                )

            # Anonymous user should still have full 60 requests
            for i in range(60):
                resp = client.get("/test-endpoint")
                assert resp.status_code == 200, f"Anon request {i+1} failed"

            # 61st anonymous request should be blocked
            resp = client.get("/test-endpoint")
            assert resp.status_code == 429

    def test_429_response_includes_retry_after(self):
        """429 responses must include a valid Retry-After header."""
        _request_counts.clear()
        # Exhaust the limit
        for _ in range(60):
            client.get("/test-endpoint")

        resp = client.get("/test-endpoint")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert retry_after > 0
        assert retry_after <= 60

    def test_x_ratelimit_reset_is_valid_unix_timestamp(self):
        """X-RateLimit-Reset should be a future Unix timestamp."""
        _request_counts.clear()
        resp = client.get("/test-endpoint")
        assert resp.status_code == 200
        reset_val = int(resp.headers["X-RateLimit-Reset"])
        now = time.time()
        # Should be in the future (within 60 seconds from now)
        assert reset_val > now - 1
        assert reset_val <= now + 61


class TestRateLimitSkipHealth:
    """Verify the /health endpoint bypasses rate limiting entirely."""

    def test_health_never_429(self):
        """/health should never be rate-limited, no matter how many requests."""
        _request_counts.clear()
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200
