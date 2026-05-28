"""Tests for tiered rate limiting middleware."""

import time
import jwt
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set JWT_SECRET before importing the middleware
os.environ["JWT_SECRET"] = "test-secret-key-for-testing"

from api.middleware.ratelimit import (
    RateLimitConfig,
    RateLimitMiddleware,
    TierConfig,
    _SlidingWindowCounter,
    _get_client_ip,
    _resolve_tier,
    create_rate_limiter,
)


JWT_SECRET = "test-secret-key-for-testing"


def _make_token(roles: list = None, expired: bool = False) -> str:
    """Helper to create a JWT token for testing."""
    import datetime
    payload = {
        "sub": "user123",
        "address": "0xabc",
        "roles": roles or [],
        "type": "access",
    }
    if expired:
        payload["exp"] = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    else:
        payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _make_app(config: RateLimitConfig = None) -> FastAPI:
    """Create a test FastAPI app with rate limiting."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config or RateLimitConfig())

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# =========================================================================
# SlidingWindowCounter tests
# =========================================================================

class TestSlidingWindowCounter:
    def test_allows_requests_under_limit(self):
        counter = _SlidingWindowCounter(window_seconds=60)
        is_limited, remaining = counter.hit("user1", limit=10)
        assert not is_limited
        assert remaining == 9

    def test_blocks_requests_over_limit(self):
        counter = _SlidingWindowCounter(window_seconds=60)
        for i in range(5):
            counter.hit("user1", limit=5)
        is_limited, retry_after = counter.hit("user1", limit=5)
        assert is_limited
        assert retry_after > 0

    def test_separate_keys_independent(self):
        counter = _SlidingWindowCounter(window_seconds=60)
        for i in range(5):
            counter.hit("user1", limit=5)
        is_limited, remaining = counter.hit("user2", limit=5)
        assert not is_limited
        assert remaining == 4

    def test_window_expiry_allows_new_requests(self):
        counter = _SlidingWindowCounter(window_seconds=1)
        for i in range(5):
            counter.hit("user1", limit=5)
        is_limited, _ = counter.hit("user1", limit=5)
        assert is_limited
        # Wait for window to expire
        time.sleep(1.1)
        is_limited, remaining = counter.hit("user1", limit=5)
        assert not is_limited
        assert remaining == 4


# =========================================================================
# Client IP extraction tests
# =========================================================================

class TestGetClientIP:
    def test_direct_ip_when_no_forwarded_header(self):
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_direct_ip_when_no_trusted_proxies_configured(self):
        """Without TRUSTED_PROXIES set, X-Forwarded-For is ignored."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "5.6.7.8"}
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_trusted_proxy_honors_forwarded_for(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1"}):
            request = MagicMock()
            request.headers = {"X-Forwarded-For": "5.6.7.8, 10.0.0.1"}
            request.client = MagicMock()
            request.client.host = "10.0.0.1"
            assert _get_client_ip(request) == "5.6.7.8"

    def test_untrusted_proxy_ignored(self):
        with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.1"}):
            request = MagicMock()
            request.headers = {"X-Forwarded-For": "5.6.7.8"}
            request.client = MagicMock()
            request.client.host = "99.99.99.99"
            assert _get_client_ip(request) == "99.99.99.99"

    def test_unknown_when_no_client(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == "unknown"


# =========================================================================
# Tier resolution tests
# =========================================================================

class TestResolveTier:
    def test_anonymous_without_token(self):
        request = MagicMock()
        request.headers = {}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "anonymous"
        assert tier.requests_per_window == 60

    def test_authenticated_with_valid_token(self):
        token = _make_token(roles=["user"])
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "authenticated"
        assert tier.requests_per_window == 300

    def test_premium_with_premium_role(self):
        token = _make_token(roles=["premium", "user"])
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "premium"
        assert tier.requests_per_window == 1000

    def test_anonymous_with_expired_token(self):
        token = _make_token(roles=["user"], expired=True)
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "anonymous"

    def test_anonymous_with_invalid_token(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid.token.here"}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "anonymous"

    def test_anonymous_with_api_key_header(self):
        """X-API-Key that is an invalid JWT falls back to anonymous."""
        request = MagicMock()
        request.headers = {"X-API-Key": "not-a-jwt"}
        config = RateLimitConfig()
        tier = _resolve_tier(request, config)
        assert tier.name == "anonymous"


# =========================================================================
# Integration tests (via TestClient)
# =========================================================================

class TestRateLimitIntegration:
    def test_health_endpoint_bypasses_rate_limit(self):
        app = _make_app()
        client = TestClient(app)
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_anonymous_rate_limit_enforced(self):
        app = _make_app()
        client = TestClient(app)
        # 60 requests should succeed
        for _ in range(60):
            resp = client.get("/test")
            assert resp.status_code == 200
        # 61st should be rate limited
        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert data["tier"] == "anonymous"

    def test_authenticated_gets_higher_limit(self):
        token = _make_token(roles=["user"])
        app = _make_app()
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        # 61-300 should succeed (anonymous would have been blocked at 61)
        for i in range(61):
            resp = client.get("/test", headers=headers)
            assert resp.status_code == 200, f"Request {i+1} failed"

    def test_premium_gets_highest_limit(self):
        token = _make_token(roles=["premium"])
        app = _make_app()
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        # 301 requests should succeed
        for i in range(301):
            resp = client.get("/test", headers=headers)
            assert resp.status_code == 200, f"Request {i+1} failed"

    def test_response_has_ratelimit_headers(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "60"
        assert resp.headers["X-RateLimit-Tier"] == "anonymous"

    def test_authenticated_tier_header(self):
        token = _make_token(roles=["user"])
        app = _make_app()
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/test", headers=headers)
        assert resp.headers["X-RateLimit-Limit"] == "300"
        assert resp.headers["X-RateLimit-Tier"] == "authenticated"

    def test_premium_tier_header(self):
        token = _make_token(roles=["premium"])
        app = _make_app()
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/test", headers=headers)
        assert resp.headers["X-RateLimit-Limit"] == "1000"
        assert resp.headers["X-RateLimit-Tier"] == "premium"

    def test_rate_limit_response_includes_tier(self):
        app = _make_app()
        client = TestClient(app)
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert "tier" in data
        assert data["tier"] == "anonymous"
        assert "retry_after" in data

    def test_legacy_create_rate_limiter_factory(self):
        """The old create_rate_limiter() still returns a middleware."""
        limiter = create_rate_limiter(requests_per_minute=50, burst=10)
        assert isinstance(limiter, RateLimitMiddleware)


# =========================================================================
# Config tests
# =========================================================================

class TestRateLimitConfig:
    def test_default_tiers(self):
        config = RateLimitConfig()
        assert config.anonymous.requests_per_window == 60
        assert config.authenticated.requests_per_window == 300
        assert config.premium.requests_per_window == 1000

    def test_custom_tiers(self):
        config = RateLimitConfig(
            anonymous=TierConfig("anon", 10),
            authenticated=TierConfig("auth", 50),
            premium=TierConfig("prem", 200),
        )
        assert config.anonymous.requests_per_window == 10
        assert config.authenticated.requests_per_window == 50
        assert config.premium.requests_per_window == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
