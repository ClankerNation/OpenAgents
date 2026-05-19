"""Tests for three-tier rate limiting middleware."""

import time
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    _get_tier,
    _request_counts,
    TIER_LIMITS,
    WINDOW_SECONDS,
)

# Test JWT secret and tokens
TEST_SECRET = "test-secret-key-for-testing-only"


def _make_token(address: str = "0x1234", roles: list = None) -> str:
    payload = {
        "sub": address,
        "address": address,
        "roles": roles or [],
        "type": "access",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _make_premium_token() -> str:
    return _make_token(roles=["premium"])


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limit counters before each test."""
    for tier in _request_counts:
        _request_counts[tier].clear()
    yield


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.add_middleware(RateLimitMiddleware)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTierDetection:
    """Verify tier is correctly determined from request auth state."""

    def test_anonymous_no_header(self):
        """Requests without Authorization header → anonymous tier."""
        class MockRequest:
            headers = {}
            client = type("obj", (object,), {"host": "1.2.3.4"})()
        assert _get_tier(MockRequest()) == "anonymous"

    def test_anonymous_empty_bearer(self):
        """Requests with empty Bearer token → anonymous."""
        class MockRequest:
            headers = {"Authorization": "Bearer "}
            client = type("obj", (object,), {"host": "1.2.3.4"})()
        assert _get_tier(MockRequest()) == "anonymous"

    def test_authenticated_valid_jwt(self):
        """Requests with valid JWT → authenticated."""
        token = _make_token()
        class MockRequest:
            headers = {"Authorization": f"Bearer {token}"}
            client = type("obj", (object,), {"host": "1.2.3.4"})()
        assert _get_tier(MockRequest()) == "authenticated"

    def test_premium_role(self):
        """Requests with JWT containing premium role → premium."""
        token = _make_premium_token()
        class MockRequest:
            headers = {"Authorization": f"Bearer {token}"}
            client = type("obj", (object,), {"host": "1.2.3.4"})()
        assert _get_tier(MockRequest()) == "premium"

    def test_invalid_jwt_falls_to_anonymous(self):
        """Requests with invalid JWT → anonymous (graceful degradation)."""
        class MockRequest:
            headers = {"Authorization": "Bearer definitely-not-a-valid-token"}
            client = type("obj", (object,), {"host": "1.2.3.4"})()
        assert _get_tier(MockRequest()) == "anonymous"


class TestHeaderPresence:
    """Verify all required headers appear in responses."""

    def test_anonymous_headers(self, client):
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == str(TIER_LIMITS["anonymous"])
        assert resp.headers.get("X-RateLimit-Remaining") is not None
        assert resp.headers.get("X-RateLimit-Reset") is not None

    def test_authenticated_headers(self, client):
        token = _make_token()
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == str(TIER_LIMITS["authenticated"])
        assert resp.headers.get("X-RateLimit-Remaining") is not None
        assert resp.headers.get("X-RateLimit-Reset") is not None

    def test_premium_headers(self, client):
        token = _make_premium_token()
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == str(TIER_LIMITS["premium"])
        assert resp.headers.get("X-RateLimit-Remaining") is not None
        assert resp.headers.get("X-RateLimit-Reset") is not None


class Test429Response:
    """Verify rate-limited requests get proper 429 response."""

    def test_anonymous_429_retry_after(self, client):
        """Anonymous tier: exhaust limit then get 429 with Retry-After."""
        limit = TIER_LIMITS["anonymous"]
        for _ in range(limit):
            resp = client.get("/test")
            assert resp.status_code == 200

        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert "retry_after" in data
        assert data["error"] == "Rate limit exceeded"
        assert resp.headers.get("Retry-After") is not None
        assert resp.headers.get("X-RateLimit-Limit") == str(limit)
        assert resp.headers.get("X-RateLimit-Remaining") == "0"
        assert resp.headers.get("X-RateLimit-Reset") is not None

    def test_authenticated_429_retry_after(self, client):
        """Authenticated tier: exhaust limit then get 429 with Retry-After."""
        limit = TIER_LIMITS["authenticated"]
        token = _make_token()
        for _ in range(limit):
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200

        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "Rate limit exceeded"
        assert resp.headers.get("Retry-After") is not None

    def test_premium_429_retry_after(self, client):
        """Premium tier: exhaust limit then get 429."""
        limit = TIER_LIMITS["premium"]
        token = _make_premium_token()
        for _ in range(limit):
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200

        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") is not None

    def test_tier_separation(self, client):
        """Anonymous and authenticated tiers should have independent counters."""
        anon_limit = TIER_LIMITS["anonymous"]
        token = _make_token()

        for _ in range(anon_limit):
            client.get("/test")

        resp = client.get("/test")
        assert resp.status_code == 429

        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        remaining = int(resp.headers["X-RateLimit-Remaining"])
        assert remaining == TIER_LIMITS["authenticated"] - 1

    def test_health_endpoint_bypass(self, client):
        """Health endpoint should not be rate limited."""
        limit = TIER_LIMITS["anonymous"]
        for _ in range(limit):
            client.get("/test")

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestPremiumApiKey:
    """Verify premium API key detection via X-Api-Key header."""

    def test_premium_via_api_key_header(self, client):
        """X-Api-Key header with premium token → premium tier."""
        token = _make_premium_token()
        resp = client.get(
            "/test",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Api-Key": "sk-premium-key",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == str(TIER_LIMITS["premium"])
