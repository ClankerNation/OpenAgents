"""Tests for tiered rate limiting middleware."""

import time
import jwt
import os
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["PREMIUM_API_KEY_1"] = "premium-key-123"

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    _get_auth_tier,
    RATE_LIMITS,
    WINDOW_SECONDS,
    _request_counts,
)


def create_test_app():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def make_request(client, headers=None):
    return client.get("/test", headers=headers or {})


def make_jwt_token(user_id="user123", expired=False):
    secret = os.environ["JWT_SECRET"]
    exp = time.time() - 3600 if expired else time.time() + 3600
    payload = {"sub": user_id, "exp": exp, "type": "access"}
    return jwt.encode(payload, secret, algorithm="HS256")


class TestRateLimitTiers:
    def setup_method(self):
        _request_counts.clear()

    def test_anonymous_tier_default(self):
        app = create_test_app()
        client = TestClient(app)
        resp = make_request(client)
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "60"
        assert resp.headers["X-RateLimit-Remaining"] == "59"
        assert "X-RateLimit-Reset" in resp.headers

    def test_authenticated_tier_higher_limit(self):
        app = create_test_app()
        client = TestClient(app)
        token = make_jwt_token()
        resp = make_request(client, {"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "300"
        assert resp.headers["X-RateLimit-Remaining"] == "299"

    def test_premium_tier_highest_limit(self):
        app = create_test_app()
        client = TestClient(app)
        resp = make_request(client, {"X-API-Key": "premium-key-123"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "1000"
        assert resp.headers["X-RateLimit-Remaining"] == "999"

    def test_invalid_token_falls_back_to_anonymous(self):
        app = create_test_app()
        client = TestClient(app)
        resp = make_request(client, {"Authorization": "Bearer invalid-token"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "60"

    def test_expired_token_falls_back_to_anonymous(self):
        app = create_test_app()
        client = TestClient(app)
        token = make_jwt_token(expired=True)
        resp = make_request(client, {"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "60"


class TestRateLimit429:
    def setup_method(self):
        _request_counts.clear()

    def test_anonymous_429_after_limit(self):
        app = create_test_app()
        client = TestClient(app)
        for _ in range(60):
            make_request(client)
        resp = make_request(client)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.json()["tier"] == "anonymous"

    def test_authenticated_429_after_limit(self):
        app = create_test_app()
        client = TestClient(app)
        token = make_jwt_token()
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(300):
            make_request(client, headers)
        resp = make_request(client, headers)
        assert resp.status_code == 429
        assert resp.json()["tier"] == "authenticated"

    def test_premium_429_after_limit(self):
        app = create_test_app()
        client = TestClient(app)
        headers = {"X-API-Key": "premium-key-123"}
        for _ in range(1000):
            make_request(client, headers)
        resp = make_request(client, headers)
        assert resp.status_code == 429
        assert resp.json()["tier"] == "premium"


class TestHeaders:
    def setup_method(self):
        _request_counts.clear()

    def test_all_rate_limit_headers_present(self):
        app = create_test_app()
        client = TestClient(app)
        resp = make_request(client)
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_health_endpoint_no_rate_limit(self):
        app = create_test_app()
        client = TestClient(app)
        for _ in range(100):
            resp = client.get("/health")
            assert resp.status_code == 200


class TestGetAuthTier:
    def setup_method(self):
        _request_counts.clear()

    def test_anonymous_no_auth(self):
        request = MagicMock()
        request.headers = {}
        assert _get_auth_tier(request) == "anonymous"

    def test_authenticated_valid_jwt(self):
        token = make_jwt_token()
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        assert _get_auth_tier(request) == "authenticated"

    def test_premium_api_key(self):
        request = MagicMock()
        request.headers = {"X-API-Key": "premium-key-123"}
        assert _get_auth_tier(request) == "premium"

    def test_invalid_api_key_not_premium(self):
        request = MagicMock()
        request.headers = {"X-API-Key": "wrong-key"}
        assert _get_auth_tier(request) == "anonymous"
