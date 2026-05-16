"""Tests for tiered rate limiting in the OpenAgents API."""

import os
import time
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitConfig,
    RateLimitTier,
    _request_counts,
)


# Test app setup
def create_test_app():
    """Create a fresh test app with rate limiting."""
    app = FastAPI()
    config = RateLimitConfig(window_seconds=60)
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limit counters before each test."""
    _request_counts.clear()
    yield
    _request_counts.clear()


@pytest.fixture
def jwt_secret():
    """Set up JWT secret for tests."""
    secret = "test-secret-key"
    os.environ["JWT_SECRET"] = secret
    yield secret
    os.environ.pop("JWT_SECRET", None)


def create_jwt_token(secret: str, user_id: str, premium: bool = False) -> str:
    """Create a test JWT token."""
    payload = {
        "sub": user_id,
        "type": "access",
        "premium": premium,
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class TestRateLimitTiers:
    """Test that different auth states get different rate limits."""

    def test_anonymous_tier_limit(self):
        """Test anonymous users get 60 req/min limit."""
        app = create_test_app()
        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "60"

    def test_authenticated_tier_limit(self, jwt_secret):
        """Test JWT authenticated users get 300 req/min limit."""
        app = create_test_app()
        client = TestClient(app)

        token = create_jwt_token(jwt_secret, "user123")
        response = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "300"

    def test_premium_tier_limit(self, jwt_secret):
        """Test premium users get 1000 req/min limit."""
        app = create_test_app()
        client = TestClient(app)

        token = create_jwt_token(jwt_secret, "premium_user", premium=True)
        response = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "1000"

    def test_premium_api_key_tier(self):
        """Test premium API keys (pk_ prefix) get 1000 req/min."""
        app = create_test_app()
        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": "pk_live_abc123xyz"},
        )

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "1000"

    def test_regular_api_key_tier(self):
        """Test regular API keys get 300 req/min."""
        app = create_test_app()
        client = TestClient(app)

        response = client.get(
            "/test",
            headers={"X-API-Key": "sk_live_abc123xyz"},
        )

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "300"


class TestRateLimitHeaders:
    """Test rate limit headers are present in responses."""

    def test_headers_in_success_response(self):
        """Test X-RateLimit-* headers in successful response."""
        app = create_test_app()
        client = TestClient(app)

        response = client.get("/test")

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_remaining_decrements(self):
        """Test remaining count decrements with each request."""
        app = create_test_app()
        client = TestClient(app)

        response1 = client.get("/test")
        remaining1 = int(response1.headers["X-RateLimit-Remaining"])

        response2 = client.get("/test")
        remaining2 = int(response2.headers["X-RateLimit-Remaining"])

        assert remaining2 == remaining1 - 1


class TestRateLimitEnforcement:
    """Test that rate limits are actually enforced."""

    def test_429_when_limit_exceeded(self):
        """Test 429 response when rate limit is exceeded."""
        app = create_test_app()
        client = TestClient(app)

        # Exhaust the anonymous limit (60 requests)
        for i in range(60):
            response = client.get("/test")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/test")
        assert response.status_code == 429

    def test_429_includes_retry_after(self):
        """Test 429 response includes Retry-After header."""
        app = create_test_app()
        client = TestClient(app)

        # Exhaust limit
        for _ in range(60):
            client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

    def test_429_response_body(self):
        """Test 429 response body contains error details."""
        app = create_test_app()
        client = TestClient(app)

        # Exhaust limit
        for _ in range(60):
            client.get("/test")

        response = client.get("/test")
        data = response.json()

        assert data["error"] == "Rate limit exceeded"
        assert data["tier"] == "anonymous"
        assert data["limit"] == 60
        assert "retry_after" in data


class TestHealthEndpointBypass:
    """Test that health endpoint bypasses rate limiting."""

    def test_health_not_rate_limited(self):
        """Test /health endpoint is not rate limited."""
        app = create_test_app()
        client = TestClient(app)

        # Make many requests to health endpoint
        for _ in range(100):
            response = client.get("/health")
            assert response.status_code == 200

        # Should still work
        response = client.get("/health")
        assert response.status_code == 200
