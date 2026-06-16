"""
Tests for rate limit middleware.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from api.middleware.ratelimit import RateLimitMiddleware, TIER_LIMITS, _determine_tier


@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRateLimitTiers:
    def test_anonymous_tier_has_lower_limit(self):
        """Anonymous tier should have 60 req/min limit."""
        assert TIER_LIMITS["anonymous"].requests_per_window == 60

    def test_authenticated_tier_has_higher_limit(self):
        """Authenticated tier should have 300 req/min limit."""
        assert TIER_LIMITS["authenticated"].requests_per_window == 300

    def test_premium_tier_has_highest_limit(self):
        """Premium tier should have 1000 req/min limit."""
        assert TIER_LIMITS["premium"].requests_per_window == 1000


class TestRateLimitHeaders:
    def test_response_includes_rate_limit_headers(self, client):
        """Every response should include X-RateLimit-* headers."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_anonymous_default_limit_header(self, client):
        """Default (anonymous) should show limit of 60."""
        response = client.get("/test")
        assert response.headers["X-RateLimit-Limit"] == "60"

    def test_authenticated_gets_higher_limit(self, client):
        """Authenticated request should show limit of 300."""
        response = client.get("/test", headers={"Authorization": "Bearer valid_token_123"})
        assert response.headers["X-RateLimit-Limit"] == "300"

    def test_premium_gets_highest_limit(self, client):
        """Premium request should show limit of 1000."""
        response = client.get("/test", headers={
            "Authorization": "Bearer premium_token_123",
            "X-API-Key": "pk_live_abc123",
        })
        assert response.headers["X-RateLimit-Limit"] == "1000"


class TestRateLimit429:
    def test_429_includes_retry_after(self, client):
        """429 response must include Retry-After header."""
        response = None
        for i in range(61):
            response = client.get("/test")
        assert response is not None
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_429_body_includes_retry_after(self, client):
        """429 body should include retry_after field."""
        response = None
        for i in range(61):
            response = client.get("/test")
        assert response is not None
        assert response.status_code == 429
        data = response.json()
        assert "retry_after" in data
        assert data["retry_after"] > 0

    def test_429_includes_rate_limit_headers(self, client):
        """429 response should still include rate limit headers."""
        response = None
        for i in range(61):
            response = client.get("/test")
        assert response is not None
        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers


class TestTierDetection:
    def test_no_auth_is_anonymous(self):
        """Request without Authorization header is anonymous."""
        scope = {"type": "http", "method": "GET", "path": "/test", "headers": []}
        request = Request(scope)
        assert _determine_tier(request) == "anonymous"

    def test_bearer_token_is_authenticated(self):
        """Request with Bearer token is authenticated."""
        scope = {
            "type": "http", "method": "GET", "path": "/test",
            "headers": [(b"authorization", b"Bearer some_token")]
        }
        request = Request(scope)
        assert _determine_tier(request) == "authenticated"

    def test_api_key_is_premium(self):
        """Request with X-API-Key is premium."""
        scope = {
            "type": "http", "method": "GET", "path": "/test",
            "headers": [
                (b"authorization", b"Bearer some_token"),
                (b"x-api-key", b"pk_live_abc"),
            ]
        }
        request = Request(scope)
        assert _determine_tier(request) == "premium"


class TestHealthEndpoint:
    def test_health_exempt_from_rate_limiting(self, client):
        """Health endpoint should not be rate limited."""
        for i in range(100):
            response = client.get("/health")
            assert response.status_code == 200
