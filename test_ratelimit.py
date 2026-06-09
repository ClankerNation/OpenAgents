"""Tests for rate limiting with tiered auth differentiation.

Verifies:
- Three tiers: anonymous (60), standard (300), premium (1000)
- X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset headers
- 429 response with Retry-After header
- Tier determined from request auth state
"""

import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import RateLimitMiddleware

# Create a minimal test app with the rate limiter
app = FastAPI()


@app.get("/test")
async def test_endpoint():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Add rate limiter middleware
app.add_middleware(RateLimitMiddleware)

client = TestClient(app)


def _reset_rate_limit_store():
    """Reset the in-memory rate limit store between tests."""
    from api.middleware.ratelimit import _request_log, _last_cleanup
    _request_log.clear()
    _last_cleanup = time.time()


def test_anonymous_tier_has_correct_limit():
    """Verify anonymous tier is 60 req/min."""
    response = client.get("/test")
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "60"


def test_standard_tier_has_correct_limit():
    """Verify standard (JWT) tier is 300 req/min."""
    response = client.get(
        "/test",
        headers={"Authorization": "Bearer test.jwt.token.here"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "300"


def test_premium_tier_has_correct_limit():
    """Verify premium (API Key) tier is 1000 req/min."""
    response = client.get(
        "/test",
        headers={"X-API-Key": "test-premium-api-key-12345"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "1000"


def test_rate_limit_headers_present():
    """Verify X-RateLimit-* headers are present on every response."""
    response = client.get("/test")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_remaining_decreases_with_requests():
    """Verify remaining count decreases as requests are made."""
    _reset_rate_limit_store()

    responses = []
    for _ in range(3):
        resp = client.get("/test")
        responses.append(resp)

    remaining_values = [int(r.headers["X-RateLimit-Remaining"]) for r in responses]
    # Each request should decrease remaining by 1
    assert remaining_values[0] == 59
    assert remaining_values[1] == 58
    assert remaining_values[2] == 57


def test_anonymous_429_after_limit():
    """Verify anonymous gets 429 after exceeding 60 requests."""
    _reset_rate_limit_store()

    responses = []
    for _ in range(62):
        resp = client.get("/test")
        responses.append(resp)

    # First 60 should be 200, next should be 429
    success_count = sum(1 for r in responses if r.status_code == 200)
    fail_count = sum(1 for r in responses if r.status_code == 429)

    assert success_count == 60, f"Expected 60 successful, got {success_count}"
    assert fail_count >= 1, f"Expected at least 1 429, got {fail_count}"

    # Check Retry-After header on 429
    for r in responses:
        if r.status_code == 429:
            assert "Retry-After" in r.headers
            retry_after = int(r.headers["Retry-After"])
            assert retry_after > 0
            break


def test_premium_tier_not_limited_under_limit():
    """Verify premium tier doesn't hit 429 below its limit."""
    _reset_rate_limit_store()

    for _ in range(100):
        resp = client.get(
            "/test",
            headers={"X-API-Key": "premium-key-12345678"},
        )
        if resp.status_code == 429:
            body = resp.json()
            assert body.get("tier") != "premium", (
                "Premium tier should not be rate limited at 100 requests"
            )
            break
        assert resp.status_code == 200

    # Verify premium tier has higher limit
    resp = client.get(
        "/test",
        headers={"X-API-Key": "premium-key-12345678"},
    )
    assert resp.headers.get("X-RateLimit-Limit") == "1000"


def test_auth_tier_detection():
    """Verify tier detection from request headers."""
    _reset_rate_limit_store()

    # No auth -> anonymous
    resp = client.get("/test")
    assert resp.headers.get("X-RateLimit-Limit") == "60"

    # Bearer token -> standard
    resp = client.get("/test", headers={"Authorization": "Bearer test-token"})
    assert resp.headers.get("X-RateLimit-Limit") == "300"

    # X-API-Key -> premium
    resp = client.get("/test", headers={"X-API-Key": "test-key-12345678"})
    assert resp.headers.get("X-RateLimit-Limit") == "1000"

    # Both headers -> premium takes priority
    resp = client.get("/test", headers={
        "Authorization": "Bearer test-token",
        "X-API-Key": "test-key-12345678",
    })
    assert resp.headers.get("X-RateLimit-Limit") == "1000"


def test_health_endpoint_not_rate_limited():
    """Verify health endpoint is exempt from rate limiting."""
    _reset_rate_limit_store()

    for _ in range(200):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_429_includes_retry_after():
    """Verify 429 response includes Retry-After header."""
    _reset_rate_limit_store()

    # Exhaust anonymous limit
    for _ in range(61):
        client.get("/test")

    resp = client.get("/test")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after > 0
    assert retry_after <= 60

    # Verify 429 body includes useful info
    body = resp.json()
    assert "error" in body
    assert "retry_after" in body
    assert "tier" in body
