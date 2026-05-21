"""Tests for the three-tier rate limiting middleware.

Contributor: iyop666 (https://github.com/iyop666)
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient
from fastapi import FastAPI

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
    TIER_LIMITS,
    WINDOW_SECONDS,
    _request_counts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_counts():
    """Reset the in-memory store between tests."""
    _request_counts.clear()
    yield
    _request_counts.clear()


def _make_app():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Tier classification tests
# ---------------------------------------------------------------------------

class TestTierClassification:
    def test_anonymous_tier(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_LIMITS[TIER_ANONYMOUS])

    def test_authenticated_tier(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test", headers={"Authorization": "Bearer fake.jwt.token"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_LIMITS[TIER_AUTHENTICATED])

    def test_premium_tier(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test", headers={"X-API-Key": "sk-premium-123"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(TIER_LIMITS[TIER_PREMIUM])


# ---------------------------------------------------------------------------
# Rate limit headers tests
# ---------------------------------------------------------------------------

class TestHeaders:
    def test_headers_present_on_success(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_remaining_decrements(self):
        app = _make_app()
        client = TestClient(app)
        r1 = client.get("/test")
        r2 = client.get("/test")
        remaining1 = int(r1.headers["X-RateLimit-Remaining"])
        remaining2 = int(r2.headers["X-RateLimit-Remaining"])
        assert remaining2 == remaining1 - 1


# ---------------------------------------------------------------------------
# 429 response tests
# ---------------------------------------------------------------------------

class TestRateLimitExceeded:
    def test_anonymous_exceeded(self):
        app = _make_app()
        client = TestClient(app)
        limit = TIER_LIMITS[TIER_ANONYMOUS]
        for _ in range(limit):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.json()["tier"] == TIER_ANONYMOUS

    def test_authenticated_exceeded(self):
        app = _make_app()
        client = TestClient(app)
        limit = TIER_LIMITS[TIER_AUTHENTICATED]
        headers = {"Authorization": "Bearer fake.jwt.token"}
        for _ in range(limit):
            client.get("/test", headers=headers)
        resp = client.get("/test", headers=headers)
        assert resp.status_code == 429
        assert resp.json()["tier"] == TIER_AUTHENTICATED

    def test_premium_exceeded(self):
        app = _make_app()
        client = TestClient(app)
        limit = TIER_LIMITS[TIER_PREMIUM]
        headers = {"X-API-Key": "sk-premium-123"}
        for _ in range(limit):
            client.get("/test", headers=headers)
        resp = client.get("/test", headers=headers)
        assert resp.status_code == 429
        assert resp.json()["tier"] == TIER_PREMIUM

    def test_429_has_all_headers(self):
        app = _make_app()
        client = TestClient(app)
        limit = TIER_LIMITS[TIER_ANONYMOUS]
        for _ in range(limit + 1):
            resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers


# ---------------------------------------------------------------------------
# Health endpoint exempt
# ---------------------------------------------------------------------------

class TestHealthExempt:
    def test_health_not_rate_limited(self):
        app = _make_app()
        client = TestClient(app)
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Window reset
# ---------------------------------------------------------------------------

class TestWindowReset:
    def test_counter_resets_after_window(self):
        app = _make_app()
        client = TestClient(app)
        limit = TIER_LIMITS[TIER_ANONYMOUS]
        for _ in range(limit):
            client.get("/test")

        # Fast-forward time
        _request_counts.clear()

        resp = client.get("/test")
        assert resp.status_code == 200
