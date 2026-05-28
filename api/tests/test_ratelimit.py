"""Tests for tiered rate limiting middleware."""

import pytest
import sys
import os
import time
import jwt
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.middleware.ratelimit as ratelimit_module
from api.middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitConfig,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
    TIER_LIMITS,
    _request_counts,
    _detect_tier,
)

TEST_JWT_SECRET = "test-secret"
JWT_ALGORITHM = "HS256"


def _make_app(config: RateLimitConfig = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _make_token(roles: list = None, user_id: str = "user123") -> str:
    payload = {"sub": user_id, "roles": roles or [], "type": "access"}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(autouse=True)
def setup():
    _request_counts.clear()
    with patch.object(ratelimit_module, "JWT_SECRET", TEST_JWT_SECRET):
        yield
    _request_counts.clear()


class TestTierDetection:
    def test_anonymous_without_token(self):
        app = _make_app()
        with TestClient(app) as client:
            request = client.build_request("GET", "/test")
            tier = _detect_tier(request)
            assert tier == TIER_ANONYMOUS

    def test_authenticated_with_valid_token(self):
        app = _make_app()
        token = _make_token()
        with TestClient(app) as client:
            request = client.build_request(
                "GET", "/test", headers={"Authorization": f"Bearer {token}"}
            )
            tier = _detect_tier(request)
            assert tier == TIER_AUTHENTICATED

    def test_premium_with_premium_role(self):
        app = _make_app()
        token = _make_token(roles=["premium"])
        with TestClient(app) as client:
            request = client.build_request(
                "GET", "/test", headers={"Authorization": f"Bearer {token}"}
            )
            tier = _detect_tier(request)
            assert tier == TIER_PREMIUM

    def test_anonymous_with_invalid_token(self):
        app = _make_app()
        with TestClient(app) as client:
            request = client.build_request(
                "GET", "/test", headers={"Authorization": "Bearer invalid.token.here"}
            )
            tier = _detect_tier(request)
            assert tier == TIER_ANONYMOUS

    def test_anonymous_with_expired_token(self):
        app = _make_app()
        payload = {"sub": "user123", "roles": [], "type": "access", "exp": 0}
        expired_token = jwt.encode(payload, TEST_JWT_SECRET, algorithm=JWT_ALGORITHM)
        with TestClient(app) as client:
            request = client.build_request(
                "GET", "/test", headers={"Authorization": f"Bearer {expired_token}"}
            )
            tier = _detect_tier(request)
            assert tier == TIER_ANONYMOUS


class TestAnonymousTier:
    def test_anonymous_limit_is_60(self):
        config = RateLimitConfig(anonymous_limit=60)
        app = _make_app(config)
        with TestClient(app) as client:
            for i in range(60):
                response = client.get("/test")
                assert response.status_code == 200
            response = client.get("/test")
            assert response.status_code == 429

    def test_anonymous_headers_present(self):
        config = RateLimitConfig(anonymous_limit=10)
        app = _make_app(config)
        with TestClient(app) as client:
            response = client.get("/test")
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "10"


class TestAuthenticatedTier:
    def test_authenticated_limit_is_300(self):
        config = RateLimitConfig(authenticated_limit=5)
        app = _make_app(config)
        token = _make_token()
        headers = {"Authorization": f"Bearer {token}"}
        with TestClient(app) as client:
            for i in range(5):
                response = client.get("/test", headers=headers)
                assert response.status_code == 200
            response = client.get("/test", headers=headers)
            assert response.status_code == 429

    def test_authenticated_higher_than_anonymous(self):
        config = RateLimitConfig(anonymous_limit=2, authenticated_limit=5)
        app = _make_app(config)
        token = _make_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        with TestClient(app) as client:
            client.get("/test")
            client.get("/test")
            anon_response = client.get("/test")
            assert anon_response.status_code == 429

            for i in range(5):
                response = client.get("/test", headers=auth_headers)
                assert response.status_code == 200


class TestPremiumTier:
    def test_premium_limit_is_1000(self):
        config = RateLimitConfig(premium_limit=5)
        app = _make_app(config)
        token = _make_token(roles=["premium"])
        headers = {"Authorization": f"Bearer {token}"}
        with TestClient(app) as client:
            for i in range(5):
                response = client.get("/test", headers=headers)
                assert response.status_code == 200
            response = client.get("/test", headers=headers)
            assert response.status_code == 429

    def test_premium_higher_than_authenticated(self):
        config = RateLimitConfig(authenticated_limit=2, premium_limit=5)
        app = _make_app(config)
        auth_token = _make_token(user_id="auth_user")
        premium_token = _make_token(roles=["premium"], user_id="premium_user")
        auth_headers = {"Authorization": f"Bearer {auth_token}"}
        premium_headers = {"Authorization": f"Bearer {premium_token}"}
        with TestClient(app) as client:
            client.get("/test", headers=auth_headers)
            client.get("/test", headers=auth_headers)
            auth_response = client.get("/test", headers=auth_headers)
            assert auth_response.status_code == 429

            for i in range(5):
                response = client.get("/test", headers=premium_headers)
                assert response.status_code == 200


class TestRateLimitHeaders:
    def test_remaining_decreases(self):
        config = RateLimitConfig(anonymous_limit=5)
        app = _make_app(config)
        with TestClient(app) as client:
            r1 = client.get("/test")
            assert r1.headers["X-RateLimit-Remaining"] == "4"
            r2 = client.get("/test")
            assert r2.headers["X-RateLimit-Remaining"] == "3"

    def test_reset_header_is_timestamp(self):
        config = RateLimitConfig(anonymous_limit=5)
        app = _make_app(config)
        with TestClient(app) as client:
            response = client.get("/test")
            reset = int(response.headers["X-RateLimit-Reset"])
            assert reset > time.time()

    def test_429_has_retry_after_header(self):
        config = RateLimitConfig(anonymous_limit=1)
        app = _make_app(config)
        with TestClient(app) as client:
            client.get("/test")
            response = client.get("/test")
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert int(response.headers["Retry-After"]) >= 1

    def test_429_has_all_rate_limit_headers(self):
        config = RateLimitConfig(anonymous_limit=1)
        app = _make_app(config)
        with TestClient(app) as client:
            client.get("/test")
            response = client.get("/test")
            assert response.status_code == 429
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
            assert response.headers["X-RateLimit-Remaining"] == "0"


class TestHealthEndpointBypass:
    def test_health_not_rate_limited(self):
        config = RateLimitConfig(anonymous_limit=1)
        app = _make_app(config)
        with TestClient(app) as client:
            client.get("/test")
            for _ in range(10):
                response = client.get("/health")
                assert response.status_code == 200


class Test429Response:
    def test_429_response_body(self):
        config = RateLimitConfig(anonymous_limit=1)
        app = _make_app(config)
        with TestClient(app) as client:
            client.get("/test")
            response = client.get("/test")
            assert response.status_code == 429
            data = response.json()
            assert data["error"] == "Rate limit exceeded"
            assert "retry_after" in data
            assert "tier" in data
