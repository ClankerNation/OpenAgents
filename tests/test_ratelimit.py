"""Tests for three-tier rate limiting middleware.

Tests cover:
- Anonymous tier (60 req/min)
- Authenticated tier (300 req/min)
- Premium tier (1000 req/min)
- X-RateLimit-* header presence
- 429 response with Retry-After header
"""

import time
import pytest
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitConfig,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
    DEFAULT_TIER_LIMITS,
    _request_counts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret"


def _make_jwt(roles=None, tier=None) -> str:
    payload = {"sub": "user1", "roles": roles or []}
    if tier:
        payload["tier"] = tier
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _build_app(tier_limits=None, window_seconds=60):
    """Return a minimal FastAPI app wrapped with rate-limit middleware."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(
            tier_limits=tier_limits,
            window_seconds=window_seconds,
        ),
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _clear_store():
    """Reset the global in-memory counter store between tests."""
    _request_counts.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTierDetection:
    """Verify that the correct tier is inferred from request headers."""

    def test_anonymous_when_no_auth(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_ANONYMOUS]
        )

    def test_authenticated_via_bearer(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_AUTHENTICATED]
        )

    def test_premium_via_bearer_role(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(roles=["premium"])
        resp = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_PREMIUM]
        )

    def test_premium_via_bearer_tier_field(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(tier="premium")
        resp = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_PREMIUM]
        )

    def test_authenticated_via_api_key(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping", headers={"X-API-Key": "ak_test123"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_AUTHENTICATED]
        )

    def test_premium_via_api_key_prefix(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping", headers={"X-API-Key": "pk_premium_key"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(
            DEFAULT_TIER_LIMITS[TIER_PREMIUM]
        )


class TestRateLimitHeaders:
    """Verify that every response carries the required headers."""

    def test_headers_present_on_success(self):
        app = _build_app()
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_remaining_decrements(self):
        app = _build_app(tier_limits={TIER_ANONYMOUS: 5}, window_seconds=60)
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        r1 = client.get("/ping")
        r2 = client.get("/ping")
        assert int(r1.headers["X-RateLimit-Remaining"]) == 4
        assert int(r2.headers["X-RateLimit-Remaining"]) == 3


class TestTierEnforcement:
    """Verify that each tier is enforced independently."""

    def test_anonymous_limit(self):
        limit = 5
        app = _build_app(
            tier_limits={TIER_ANONYMOUS: limit, TIER_AUTHENTICATED: 300},
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(limit):
            client.get("/ping")
        resp = client.get("/ping")
        assert resp.status_code == 429

    def test_authenticated_higher_limit(self):
        anon_limit = 5
        auth_limit = 20
        app = _build_app(
            tier_limits={
                TIER_ANONYMOUS: anon_limit,
                TIER_AUTHENTICATED: auth_limit,
            },
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()

        # Exhaust anonymous limit
        for _ in range(anon_limit):
            client.get("/ping")
        # Anonymous is now limited
        assert client.get("/ping").status_code == 429

        # Authenticated should still work
        resp = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_premium_highest_limit(self):
        app = _build_app(
            tier_limits={
                TIER_ANONYMOUS: 2,
                TIER_AUTHENTICATED: 5,
                TIER_PREMIUM: 50,
            },
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(roles=["premium"])

        # Hit many requests that would exhaust lower tiers
        for _ in range(10):
            resp = client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert int(resp.headers["X-RateLimit-Limit"]) == 50


class TestRetryAfter:
    """Verify 429 responses include Retry-After header."""

    def test_429_has_retry_after(self):
        limit = 3
        app = _build_app(
            tier_limits={TIER_ANONYMOUS: limit},
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(limit):
            client.get("/ping")
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_val = int(resp.headers["Retry-After"])
        assert 1 <= retry_val <= 60

    def test_429_body_has_tier_and_retry_after(self):
        limit = 2
        app = _build_app(
            tier_limits={TIER_ANONYMOUS: limit},
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(limit):
            client.get("/ping")
        resp = client.get("/ping")
        assert resp.status_code == 429
        body = resp.json()
        assert body["tier"] == TIER_ANONYMOUS
        assert "retry_after" in body
        assert "error" in body

    def test_429_has_all_ratelimit_headers(self):
        limit = 2
        app = _build_app(
            tier_limits={TIER_ANONYMOUS: limit},
            window_seconds=60,
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(limit):
            client.get("/ping")
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert resp.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in resp.headers


class TestHealthExempt:
    """Verify /health is exempt from rate limiting."""

    def test_health_not_rate_limited(self):
        app = _build_app(tier_limits={TIER_ANONYMOUS: 1}, window_seconds=60)
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        # Even with limit of 1, /health should always pass
        client.get("/ping")  # exhaust
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200


class TestWindowReset:
    """Verify counters reset after the window expires."""

    def test_window_resets(self):
        app = _build_app(
            tier_limits={TIER_ANONYMOUS: 2},
            window_seconds=1,  # 1-second window for fast test
        )
        _clear_store()
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping")
        client.get("/ping")
        assert client.get("/ping").status_code == 429
        time.sleep(1.1)
        assert client.get("/ping").status_code == 200
