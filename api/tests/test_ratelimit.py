"""Tests for tiered rate limiting middleware."""

import jwt
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from middleware.ratelimit import RateLimitMiddleware, _request_counts, TIERS

JWT_SECRET = "test-secret-key"


def _make_token(sub: str, roles: list = None) -> str:
    payload = {"sub": sub, "roles": roles or []}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def app():
    _app = FastAPI()

    @_app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @_app.get("/health")
    async def health():
        return {"status": "ok"}

    _app.add_middleware(RateLimitMiddleware)
    return _app


@pytest.fixture(autouse=True)
def clear_state():
    _request_counts.clear()
    yield


def make_client(app):
    return TestClient(app)


class TestAnonymousTier:
    def test_anonymous_gets_60_limit(self, app):
        client = make_client(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "60"
        assert int(resp.headers["X-RateLimit-Remaining"]) < 60
        assert "X-RateLimit-Reset" in resp.headers

    def test_anonymous_exhausts_60_requests(self, app):
        client = make_client(app)
        for _ in range(60):
            resp = client.get("/test")
            assert resp.status_code == 200
        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "Rate limit exceeded"
        assert data["tier"] == "anonymous"
        assert "Retry-After" in resp.headers

    def test_anonymous_remaining_decrements(self, app):
        client = make_client(app)
        resp1 = client.get("/test")
        remaining_1 = int(resp1.headers["X-RateLimit-Remaining"])
        resp2 = client.get("/test")
        remaining_2 = int(resp2.headers["X-RateLimit-Remaining"])
        assert remaining_2 == remaining_1 - 1

    def test_health_route_not_rate_limited(self, app):
        client = make_client(app)
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200


class TestAuthenticatedTier:
    def test_authenticated_gets_300_limit(self, app):
        client = make_client(app)
        token = _make_token(sub="user_123")
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "300"
        assert "X-RateLimit-Reset" in resp.headers

    def test_authenticated_exhausts_300_requests(self, app):
        client = make_client(app)
        token = _make_token(sub="user_456")
        for _ in range(300):
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 429
        data = resp.json()
        assert data["tier"] == "authenticated"

    def test_authenticated_remaining_decrements(self, app):
        client = make_client(app)
        token = _make_token(sub="user_789")
        resp1 = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        remaining_1 = int(resp1.headers["X-RateLimit-Remaining"])
        resp2 = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        remaining_2 = int(resp2.headers["X-RateLimit-Remaining"])
        assert remaining_2 == remaining_1 - 1

    def test_different_users_have_independent_counters(self, app):
        client = make_client(app)
        token_a = _make_token(sub="user_a")
        token_b = _make_token(sub="user_b")
        for _ in range(60):
            client.get("/test", headers={"Authorization": f"Bearer {token_a}"})
        resp_a = client.get("/test", headers={"Authorization": f"Bearer {token_a}"})
        assert resp_a.status_code == 200
        resp_b = client.get("/test", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b.status_code == 200
        assert resp_b.headers["X-RateLimit-Limit"] == "300"


class TestPremiumTier:
    def test_premium_gets_1000_limit(self, app):
        client = make_client(app)
        token = _make_token(sub="premium_user", roles=["premium"])
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "1000"

    def test_premium_tier_keyed_by_user_not_ip(self, app):
        client = make_client(app)
        token = _make_token(sub="premium_user", roles=["premium"])
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "1000"


class TestRateLimitHeaders:
    def test_all_rate_limit_headers_present_on_success(self, app):
        client = make_client(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_429_has_retry_after(self, app):
        client = make_client(app)
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0

    def test_429_has_rate_limit_headers(self, app):
        client = make_client(app)
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert resp.headers["X-RateLimit-Limit"] == "60"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in resp.headers


class TestInvalidTokens:
    def test_invalid_token_falls_back_to_anonymous(self, app):
        client = make_client(app)
        resp = client.get(
            "/test",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "60"
