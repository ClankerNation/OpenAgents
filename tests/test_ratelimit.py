"""Tests for rate limiting middleware."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {"message": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def anonymous_client(app):
    config = RateLimitConfig(anonymous_limit=5, authenticated_limit=10, premium_limit=15, window_seconds=60)
    middleware = RateLimitMiddleware(app, config)
    app.add_middleware(RateLimitMiddleware, config=config)
    return TestClient(app)


def test_anonymous_tier_limit(anonymous_client):
    """Anonymous users get 60 req/min (5 in test)."""
    for i in range(5):
        response = anonymous_client.get("/test")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "5"

    # 6th request should be rate limited
    response = anonymous_client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_rate_limit_headers_present(anonymous_client):
    """Rate limit headers present in every response."""
    response = anonymous_client.get("/test")
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_429_includes_retry_after(anonymous_client):
    """429 response includes Retry-After header."""
    for i in range(6):
        anonymous_client.get("/test")
    response = anonymous_client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


def test_health_endpoint_exempt(anonymous_client):
    """Health endpoint is exempt from rate limiting."""
    for i in range(10):
        response = anonymous_client.get("/health")
        assert response.status_code == 200


def test_authenticated_tier(anonymous_client):
    """Authenticated users get higher limits."""
    headers = {"Authorization": "Bearer test-token"}
    response = anonymous_client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "10"


def test_premium_tier(anonymous_client):
    """Premium API keys get highest limits."""
    headers = {"X-API-Key": "premium_test-key"}
    response = anonymous_client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "15"
