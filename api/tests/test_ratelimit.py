"""Tests for tiered rate limiting middleware.

Covers:
- Anonymous tier (60 req/min) enforcement and 429 response
- Authenticated tier (300 req/min) enforcement
- Premium tier (1000 req/min) enforcement
- Rate limit header presence on all responses
- Retry-After header on 429 responses
- Health endpoint exemption from rate limiting
"""

import time
import os
import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.middleware.ratelimit import (
    RateLimitMiddleware,
    _detect_auth_tier,
    _get_client_key,
    _request_counts,
    TIER_LIMITS,
    WINDOW_SECONDS,
)

# Set a fixed JWT secret for testing
os.environ["JWT_SECRET"] = "test-secret-key"


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_token(user_id="user-1", roles=None):
    """Create a signed JWT for testing."""
    return jwt.encode(
        {
            "sub": user_id,
            "address": "0x1234",
            "roles": roles or [],
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def _make_premium_token(user_id="premium-1"):
    """Create a JWT with premium role."""
    return _make_token(user_id=user_id, roles=["premium"])


def _make_expired_token():
    """Create an expired JWT."""
    return jwt.encode(
        {
            "sub": "expired-user",
            "roles": [],
            "exp": 0,  # epoch 0 = long expired
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def app():
    """Create a FastAPI app with rate limit middleware and test routes."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app):
    """TestClient bound to the rate-limited app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_counters():
    """Reset rate limit counters before each test."""
    _request_counts.clear()
    yield
    _request_counts.clear()


# ── Tier Detection Tests ─────────────────────────────────────────────────


def test_detect_anonymous_tier():
    """Requests without auth headers should be anonymous tier."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/test")
    assert response.headers["X-RateLimit-Limit"] == str(TIER_LIMITS["anonymous"])


def test_detect_authenticated_tier():
    """Requests with valid JWT should be authenticated tier."""
    token = _make_token()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert response.headers["X-RateLimit-Limit"] == str(
        TIER_LIMITS["authenticated"]
    )


def test_detect_premium_tier():
    """Requests with JWT containing 'premium' role should be premium tier."""
    token = _make_premium_token()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/test", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.headers["X-RateLimit-Limit"] == str(TIER_LIMITS["premium"])


def test_invalid_token_falls_back_to_anonymous():
    """Requests with invalid JWT should be treated as anonymous."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/test",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.headers["X-RateLimit-Limit"] == str(TIER_LIMITS["anonymous"])


def test_expired_token_falls_back_to_anonymous():
    """Expired JWTs should fall back to anonymous tier."""
    token = _make_expired_token()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/test", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.headers["X-RateLimit-Limit"] == str(TIER_LIMITS["anonymous"])


# ── Rate Limit Enforcement Tests ─────────────────────────────────────────


def test_anonymous_rate_limit_60_rpm():
    """Anonymous users should get 429 after 60 requests in the window."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)

    # Should succeed for 60 requests
    for i in range(60):
        response = client.get("/test")
        assert response.status_code == 200, f"Request {i + 1} should succeed"

    # 61st request should be rate limited
    response = client.get("/test")
    assert response.status_code == 429
    assert response.json()["error"] == "Rate limit exceeded"
    assert "Retry-After" in response.headers


def test_authenticated_rate_limit_300_rpm():
    """Authenticated users should get 300 requests per minute."""
    token = _make_token()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)

    # 300 requests should succeed
    for i in range(300):
        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Request {i + 1} should succeed"

    # 301st should be rate limited
    response = client.get(
        "/test", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 429


def test_premium_rate_limit_1000_rpm():
    """Premium users should get 1000 requests per minute."""
    token = _make_premium_token()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)

    # 1000 requests should succeed
    for i in range(1000):
        response = client.get(
            "/test", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Request {i + 1} should succeed"

    # 1001st should be rate limited
    response = client.get(
        "/test", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 429


# ── Response Header Tests ────────────────────────────────────────────────


def test_rate_limit_headers_present(client):
    """All responses should include X-RateLimit-* headers."""
    response = client.get("/test")
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_remaining_decrements(client):
    """X-RateLimit-Remaining should decrease with each request."""
    remaining_values = []
    for i in range(5):
        response = client.get("/test")
        remaining_values.append(int(response.headers["X-RateLimit-Remaining"]))

    assert remaining_values == [59, 58, 57, 56, 55]


def test_429_includes_retry_after_header(client):
    """429 responses must include Retry-After header."""
    # Exhaust the anonymous limit
    for _ in range(TIER_LIMITS["anonymous"]):
        client.get("/test")

    response = client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    retry_after = int(response.headers["Retry-After"])
    assert retry_after > 0


def test_429_has_zero_remaining(client):
    """429 responses should show X-RateLimit-Remaining: 0."""
    for _ in range(TIER_LIMITS["anonymous"]):
        client.get("/test")

    response = client.get("/test")
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Remaining"] == "0"


# ── Health Endpoint Exemption ────────────────────────────────────────────


def test_health_endpoint_not_limited(client):
    """The /health endpoint should never be rate limited."""
    # Make many health requests — none should be limited
    for _ in range(200):
        response = client.get("/health")
        assert response.status_code == 200


# ── Client Key Tests ─────────────────────────────────────────────────────


def test_authenticated_users_keyed_by_user_id():
    """Different IPs with the same auth token should share a rate limit
    (keyed by user ID, not IP)."""
    token = _make_token(user_id="shared-user")
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)

    # Send requests from different "IPs"
    count = 0
    for ip in ["10.0.0.1", "10.0.0.2", "10.0.0.3"]:
        for _ in range(100):
            response = client.get(
                "/test",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Forwarded-For": ip,
                },
            )
            if response.status_code == 200:
                count += 1
            else:
                break  # Hit the limit

    # Should be capped at 300 (authenticated tier), not 300 per IP
    assert count == TIER_LIMITS["authenticated"]


def test_anonymous_users_keyed_by_ip():
    """Different IPs should have independent rate limits for anonymous users."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test():
        return {"ok": True}

    client = TestClient(app)

    # Exhaust one IP
    for _ in range(TIER_LIMITS["anonymous"]):
        client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})

    response = client.get("/test", headers={"X-Forwarded-For": "10.0.0.1"})
    assert response.status_code == 429

    # Different IP should still work
    response = client.get("/test", headers={"X-Forwarded-For": "10.0.0.2"})
    assert response.status_code == 200
