"""Tests for tiered rate limiting middleware."""

import time
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from middleware.ratelimit import RateLimitMiddleware, _request_counts, _get_tier

JWT_SECRET = "test-secret-key"
app = FastAPI()

@app.get("/test")
async def test_endpoint():
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok"}

app.add_middleware(RateLimitMiddleware)
client = TestClient(app)


def _make_token(sub: str, roles: list = None) -> str:
    payload = {"sub": sub, "roles": roles or []}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def setup_function():
    _request_counts.clear()


class TestTierDetection:
    def test_anonymous_no_auth(self):
        req = client.build_request("GET", "/test")
        tier, limit, key = _get_tier(req)
        assert tier == "anonymous"
        assert limit == 60

    def test_authenticated_jwt(self):
        token = _make_token("user1")
        req = client.build_request("GET", "/test")
        req.headers["Authorization"] = f"Bearer {token}"
        tier, limit, key = _get_tier(req)
        assert tier == "authenticated"
        assert limit == 300

    def test_premium_jwt(self):
        token = _make_token("user1", roles=["premium"])
        req = client.build_request("GET", "/test")
        req.headers["Authorization"] = f"Bearer {token}"
        tier, limit, key = _get_tier(req)
        assert tier == "premium"
        assert limit == 1000

    def test_api_key_authenticated(self):
        req = client.build_request("GET", "/test")
        req.headers["X-API-Key"] = "key_abc123"
        tier, limit, key = _get_tier(req)
        assert tier == "authenticated"
        assert limit == 300

    def test_premium_api_key(self):
        req = client.build_request("GET", "/test")
        req.headers["X-API-Key"] = "premium_key_abc"
        tier, limit, key = _get_tier(req)
        assert tier == "premium"
        assert limit == 1000

    def test_invalid_token_falls_to_anonymous(self):
        req = client.build_request("GET", "/test")
        req.headers["Authorization"] = "Bearer invalid-token"
        tier, limit, key = _get_tier(req)
        assert tier == "anonymous"
        assert limit == 60


class TestAnonymousTier:
    def test_allowed_up_to_60(self):
        for i in range(60):
            resp = client.get("/test")
            assert resp.status_code == 200, f"failed at request {i+1}"

    def test_limited_at_61(self):
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429

    def test_rate_limit_headers_present(self):
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_anonymous_limit_header(self):
        resp = client.get("/test")
        assert resp.headers["X-RateLimit-Limit"] == "60"

    def test_retry_after_on_429(self):
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0

    def test_429_has_tier_in_body(self):
        for _ in range(60):
            client.get("/test")
        resp = client.get("/test")
        data = resp.json()
        assert data["tier"] == "anonymous"


class TestAuthenticatedTier:
    def test_allowed_up_to_300(self):
        token = _make_token("authuser")
        for i in range(300):
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, f"failed at request {i+1}"

    def test_limited_at_301(self):
        token = _make_token("authuser")
        for _ in range(300):
            client.get("/test", headers={"Authorization": f"Bearer {token}"})
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 429

    def test_authenticated_limit_header(self):
        token = _make_token("authuser")
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.headers["X-RateLimit-Limit"] == "300"


class TestPremiumTier:
    def test_allowed_up_to_1000(self):
        token = _make_token("premuser", roles=["premium"])
        for i in range(1000):
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, f"failed at request {i+1}"

    def test_limited_at_1001(self):
        token = _make_token("premuser", roles=["premium"])
        for _ in range(1000):
            client.get("/test", headers={"Authorization": f"Bearer {token}"})
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 429

    def test_premium_limit_header(self):
        token = _make_token("premuser", roles=["premium"])
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.headers["X-RateLimit-Limit"] == "1000"


class TestIndependentCounters:
    def test_different_users_independent(self):
        token_a = _make_token("usera")
        token_b = _make_token("userb")
        for _ in range(60):
            client.get("/test", headers={"Authorization": f"Bearer {token_a}"})
        resp_b = client.get("/test", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b.status_code == 200

    def test_anonymous_and_auth_independent(self):
        token = _make_token("someuser")
        for _ in range(60):
            client.get("/test")
        resp_auth = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp_auth.status_code == 200


class TestHealthEndpoint:
    def test_health_not_rate_limited(self):
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200
