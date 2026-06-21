"""Tests for three-tier rate limiting middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
import time

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    SlidingWindowCounter,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
)


@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestSlidingWindow:
    def test_under_limit(self):
        counter = SlidingWindowCounter()
        is_limited, remaining, limit, _ = counter.check("test", 10)
        assert not is_limited
        assert remaining == 9
        assert limit == 10

    def test_at_limit(self):
        counter = SlidingWindowCounter()
        for _ in range(10):
            counter.check("test", 10)
        is_limited, remaining, limit, retry_after = counter.check("test", 10)
        assert is_limited
        assert remaining == 0
        assert retry_after > 0

    def test_window_expires(self):
        counter = SlidingWindowCounter()
        for _ in range(10):
            counter.check("test", 10)

        # Simulate time passing
        with patch("time.time", return_value=time.time() + 61):
            is_limited, remaining, _, _ = counter.check("test", 10)
            assert not is_limited
            assert remaining == 9


class TestAnonymousTier:
    def test_anonymous_limit(self, client):
        """Anonymous users get 60 req/min."""
        for i in range(TIER_ANONYMOUS):
            resp = client.get("/test")
            assert resp.status_code == 200, f"Request {i+1} failed"

        resp = client.get("/test")
        assert resp.status_code == 429

    def test_anonymous_headers(self, client):
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers
        assert "X-RateLimit-Tier" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_ANONYMOUS)
        assert resp.headers["X-RateLimit-Tier"] == "anonymous"


class TestAuthenticatedTier:
    def test_authenticated_higher_limit(self, client):
        """Authenticated users get 300 req/min."""
        headers = {"Authorization": "Bearer test_token_12345"}
        for i in range(5):
            resp = client.get("/test", headers=headers)
            assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_AUTHENTICATED)
        assert resp.headers["X-RateLimit-Tier"] == "authenticated"

    def test_api_key_tier(self, client):
        """X-API-Key header also grants authenticated tier."""
        headers = {"X-API-Key": "my_api_key_12345"}
        resp = client.get("/test", headers=headers)
        assert resp.headers["X-RateLimit-Tier"] == "authenticated"


class TestPremiumTier:
    def test_premium_limit(self, client):
        """Premium keys get 1000 req/min."""
        headers = {"X-API-Key": "pk_premium_key_12345"}
        resp = client.get("/test", headers=headers)
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_PREMIUM)
        assert resp.headers["X-RateLimit-Tier"] == "premium"

    def test_premium_header(self, client):
        """X-API-Tier: premium header also grants premium tier."""
        headers = {"Authorization": "Bearer token123", "X-API-Tier": "premium"}
        resp = client.get("/test", headers=headers)
        assert resp.headers["X-RateLimit-Tier"] == "premium"


class TestHealthExempt:
    def test_health_not_rate_limited(self, client):
        """Health endpoint bypasses rate limiting."""
        for _ in range(100):
            resp = client.get("/health")
            assert resp.status_code == 200


class TestRetryAfter:
    def test_429_includes_retry_after(self, client):
        """429 response includes Retry-After header."""
        for _ in range(TIER_ANONYMOUS):
            client.get("/test")

        resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0

    def test_429_body(self, client):
        """429 response body includes tier info."""
        for _ in range(TIER_ANONYMOUS):
            client.get("/test")

        resp = client.get("/test")
        body = resp.json()
        assert body["error"] == "Rate limit exceeded"
        assert body["tier"] == "anonymous"
        assert body["limit"] == TIER_ANONYMOUS
        assert body["retry_after"] > 0
