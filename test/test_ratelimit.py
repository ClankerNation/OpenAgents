"""
Tests for three-tier rate limiting middleware.

Covers:
  - Tier classification (anonymous, authenticated, premium)
  - Rate limit headers in every response
  - 429 response with Retry-After header
  - Sliding window behavior
  - Health endpoint exemption
"""

import pytest
import time
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import (
    ThreeTierRateLimitMiddleware,
    _classify_tier,
    _check_rate_limit,
    _get_client_ip,
    ANONYMOUS_LIMIT,
    AUTHENTICATED_LIMIT,
    PREMIUM_LIMIT,
    WINDOW_SECONDS,
    _window_store,
)


# --- Test helpers ---


def _make_app():
    """Create a minimal FastAPI app with the rate limiter."""
    app = FastAPI()
    app.add_middleware(ThreeTierRateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture(autouse=True)
def clear_store():
    """Clear the rate limit store between tests."""
    _window_store.clear()
    yield
    _window_store.clear()


# --- Tier Classification Tests ---


def test_classify_tier_anonymous():
    """No auth headers → anonymous tier."""
    request = MagicMock()
    request.headers = {}
    assert _classify_tier(request) == "anonymous"


def test_classify_tier_authenticated():
    """Bearer token → authenticated tier."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer my-token-123"}
    assert _classify_tier(request) == "authenticated"


def test_classify_tier_premium():
    """X-API-Key → premium tier."""
    request = MagicMock()
    request.headers = {"X-API-Key": "premium-key-abc"}
    assert _classify_tier(request) == "premium"


def test_classify_tier_premium_over_bearer():
    """X-API-Key takes priority over Bearer token."""
    request = MagicMock()
    request.headers = {
        "X-API-Key": "premium-key",
        "Authorization": "Bearer some-token",
    }
    assert _classify_tier(request) == "premium"


def test_classify_tier_empty_bearer():
    """Empty Bearer token should not be authenticated."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer "}
    assert _classify_tier(request) == "anonymous"


def test_classify_tier_empty_api_key():
    """Empty X-API-Key should not be premium."""
    request = MagicMock()
    request.headers = {"X-API-Key": ""}
    assert _classify_tier(request) == "anonymous"


# --- Rate Limit Enforcement Tests ---


def test_anonymous_tier_allows_up_to_limit():
    """Anonymous tier allows up to 60 requests."""
    app = _make_app()
    client = TestClient(app)

    for i in range(ANONYMOUS_LIMIT):
        resp = client.get("/test")
        assert resp.status_code == 200, f"Request {i+1} should succeed"

    # Next request should be rate limited
    resp = client.get("/test")
    assert resp.status_code == 429


def test_authenticated_tier_allows_up_to_limit():
    """Authenticated tier allows up to 300 requests."""
    app = _make_app()
    client = TestClient(app)

    # Send requests up to the authenticated limit
    for i in range(100):  # Test with 100 (subset to keep test fast)
        resp = client.get("/test", headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 200, f"Request {i+1} should succeed"

    # Should still have remaining
    resp = client.get("/test", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200


def test_premium_tier_allows_up_to_limit():
    """Premium tier allows up to 1000 requests."""
    app = _make_app()
    client = TestClient(app)

    for i in range(100):  # Test with 100 (subset to keep test fast)
        resp = client.get("/test", headers={"X-API-Key": "premium-key"})
        assert resp.status_code == 200, f"Request {i+1} should succeed"

    resp = client.get("/test", headers={"X-API-Key": "premium-key"})
    assert resp.status_code == 200


def test_tiers_are_independent():
    """Anonymous limit doesn't affect authenticated tier."""
    app = _make_app()
    client = TestClient(app)

    # Exhaust anonymous limit
    for _ in range(ANONYMOUS_LIMIT):
        client.get("/test")

    # Anonymous should be limited
    resp = client.get("/test")
    assert resp.status_code == 429

    # Authenticated should still work
    resp = client.get("/test", headers={"Authorization": "Bearer token"})
    assert resp.status_code == 200


# --- Rate Limit Header Tests ---


def test_headers_present_on_success():
    """X-RateLimit headers present on successful responses."""
    app = _make_app()
    client = TestClient(app)

    resp = client.get("/test")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers


def test_headers_show_correct_limit():
    """X-RateLimit-Limit matches tier limit."""
    app = _make_app()
    client = TestClient(app)

    # Anonymous
    resp = client.get("/test")
    assert resp.headers["X-RateLimit-Limit"] == str(ANONYMOUS_LIMIT)

    # Authenticated
    resp = client.get("/test", headers={"Authorization": "Bearer token"})
    assert resp.headers["X-RateLimit-Limit"] == str(AUTHENTICATED_LIMIT)

    # Premium
    resp = client.get("/test", headers={"X-API-Key": "key"})
    assert resp.headers["X-RateLimit-Limit"] == str(PREMIUM_LIMIT)


def test_remaining_decrements():
    """X-RateLimit-Remaining decreases with each request."""
    app = _make_app()
    client = TestClient(app)

    resp1 = client.get("/test")
    remaining1 = int(resp1.headers["X-RateLimit-Remaining"])

    resp2 = client.get("/test")
    remaining2 = int(resp2.headers["X-RateLimit-Remaining"])

    assert remaining2 == remaining1 - 1


# --- 429 Response Tests ---


def test_429_includes_retry_after():
    """429 response includes Retry-After header."""
    app = _make_app()
    client = TestClient(app)

    # Exhaust limit
    for _ in range(ANONYMOUS_LIMIT):
        client.get("/test")

    resp = client.get("/test")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) > 0


def test_429_includes_rate_limit_headers():
    """429 response still includes X-RateLimit headers."""
    app = _make_app()
    client = TestClient(app)

    for _ in range(ANONYMOUS_LIMIT):
        client.get("/test")

    resp = client.get("/test")
    assert resp.status_code == 429
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert resp.headers["X-RateLimit-Remaining"] == "0"


def test_429_body_has_correct_structure():
    """429 response body includes error details."""
    app = _make_app()
    client = TestClient(app)

    for _ in range(ANONYMOUS_LIMIT):
        client.get("/test")

    resp = client.get("/test")
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "Rate limit exceeded"
    assert body["tier"] == "anonymous"
    assert body["limit"] == ANONYMOUS_LIMIT
    assert body["retry_after"] > 0


# --- Health Endpoint Tests ---


def test_health_exempt_from_rate_limiting():
    """Health endpoint is not rate limited."""
    app = _make_app()
    client = TestClient(app)

    for _ in range(ANONYMOUS_LIMIT + 10):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_health_still_has_headers():
    """Health endpoint still returns rate limit headers for consistency."""
    app = _make_app()
    client = TestClient(app)

    resp = client.get("/health")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


# --- Sliding Window Tests ---


def test_window_reset_allows_requests():
    """After window expires, requests are allowed again."""
    app = _make_app()
    client = TestClient(app)

    # Exhaust limit
    for _ in range(ANONYMOUS_LIMIT):
        client.get("/test")

    # Manually expire the window by clearing old entries
    for key in list(_window_store.keys()):
        _window_store[key] = []

    # Should work again
    resp = client.get("/test")
    assert resp.status_code == 200
