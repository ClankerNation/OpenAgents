"""
Tests for three-tier rate limiting middleware.

Run: pytest test/test_ratelimit.py -v
"""

import pytest
import time
import jwt
import os

# Ensure JWT_SECRET is set for test environment
os.environ["JWT_SECRET"] = "test-secret-key-for-ratelimit-tests"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.middleware.ratelimit import (
    RateLimitMiddleware,
    ANON_LIMIT,
    AUTH_LIMIT,
    PREMIUM_LIMIT,
    WINDOW_SECONDS,
    _request_timestamps,
)


def _make_token(sub="user1", roles=None):
    """Helper: create a signed JWT."""
    payload = {"sub": sub, "roles": roles or []}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def _make_premium_token(sub="premium1"):
    return _make_token(sub, roles=["premium"])


@pytest.fixture(autouse=True)
def clear_state():
    """Reset in-memory rate-limit state before each test."""
    _request_timestamps.clear()
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    return TestClient(app)


# ---- Anonymous tier (60 req/min) ----

def test_anon_within_limit(client):
    """60 anonymous requests should all succeed."""
    for i in range(ANON_LIMIT):
        r = client.get("/test")
        assert r.status_code == 200, f"request {i} failed"

def test_anon_exceeds_limit(client):
    """The 61st anonymous request should return 429."""
    for _ in range(ANON_LIMIT):
        client.get("/test")
    r = client.get("/test")
    assert r.status_code == 429
    assert "Rate limit exceeded" in r.json()["error"]

def test_anon_headers_present(client):
    """Anonymous responses include correct rate-limit headers."""
    r = client.get("/test")
    assert r.status_code == 200
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Reset" in r.headers
    assert r.headers["X-RateLimit-Limit"] == str(ANON_LIMIT)

# ---- Authenticated tier (300 req/min) ----

def test_auth_within_limit(client):
    """300 authenticated requests should succeed."""
    headers = {"Authorization": f"Bearer {_make_token()}"}
    for i in range(AUTH_LIMIT):
        r = client.get("/test", headers=headers)
        assert r.status_code == 200, f"request {i} failed"

def test_auth_exceeds_limit(client):
    """The 301st authenticated request should return 429."""
    headers = {"Authorization": f"Bearer {_make_token()}"}
    for _ in range(AUTH_LIMIT):
        client.get("/test", headers=headers)
    r = client.get("/test", headers=headers)
    assert r.status_code == 429

def test_auth_headers_present(client):
    """Authenticated responses include correct limit header."""
    headers = {"Authorization": f"Bearer {_make_token()}"}
    r = client.get("/test", headers=headers)
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == str(AUTH_LIMIT)

# ---- Premium tier (1000 req/min) ----

def test_premium_within_limit(client):
    """Premium tier allows 1000 requests (sampled: 50)."""
    headers = {"Authorization": f"Bearer {_make_premium_token()}"}
    for i in range(50):
        r = client.get("/test", headers=headers)
        assert r.status_code == 200, f"request {i} failed"
    assert r.headers["X-RateLimit-Limit"] == str(PREMIUM_LIMIT)

def test_premium_headers(client):
    """Premium responses include correct limit header."""
    headers = {"Authorization": f"Bearer {_make_premium_token()}"}
    r = client.get("/test", headers=headers)
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == str(PREMIUM_LIMIT)

# ---- 429 response format ----

def test_429_includes_retry_after(client):
    """429 responses must include Retry-After header."""
    for _ in range(ANON_LIMIT):
        client.get("/test")
    r = client.get("/test")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) > 0

def test_429_includes_rate_limit_headers(client):
    """429 responses include X-RateLimit-* headers."""
    for _ in range(ANON_LIMIT):
        client.get("/test")
    r = client.get("/test")
    assert r.status_code == 429
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Reset" in r.headers
    assert r.headers["X-RateLimit-Remaining"] == "0"

def test_429_body_contains_tier(client):
    """429 response body includes the tier name."""
    for _ in range(ANON_LIMIT):
        client.get("/test")
    r = client.get("/test")
    assert "tier" in r.json()

# ---- Health endpoint bypass ----

def test_health_bypasses_rate_limit(client):
    """Health endpoint should never be rate-limited."""
    for _ in range(ANON_LIMIT * 2):
        r = client.get("/health")
        assert r.status_code == 200

# ---- Separate counters per user/tier ----

def test_separate_counters_auth_and_anon(client):
    """Auth and anon counters are independent."""
    # Exhaust anonymous
    for _ in range(ANON_LIMIT):
        client.get("/test")
    # Auth should still work
    headers = {"Authorization": f"Bearer {_make_token()}"}
    r = client.get("/test", headers=headers)
    assert r.status_code == 200

def test_separate_counters_two_auth_users(client):
    """Different auth users have independent counters."""
    tok1 = _make_token("user_a")
    tok2 = _make_token("user_b")
    # Exhaust user_a
    for _ in range(AUTH_LIMIT):
        client.get("/test", headers={"Authorization": f"Bearer {tok1}"})
    # user_b should still work
    r = client.get("/test", headers={"Authorization": f"Bearer {tok2}"})
    assert r.status_code == 200

# ---- Invalid/expired token falls back to anonymous ----

def test_invalid_token_falls_to_anon(client):
    """Malformed JWT falls back to anonymous tier."""
    headers = {"Authorization": "Bearer invalid.token.here"}
    for _ in range(ANON_LIMIT):
        r = client.get("/test", headers=headers)
        assert r.status_code == 200
    r = client.get("/test", headers=headers)
    assert r.status_code == 429

def test_no_auth_header_is_anonymous(client):
    """No Authorization header → anonymous."""
    for _ in range(ANON_LIMIT):
        r = client.get("/test")
        assert r.status_code == 200
    r = client.get("/test")
    assert r.status_code == 429

# ---- X-RateLimit-Reset is a valid timestamp ----

def test_reset_is_future_timestamp(client):
    """X-RateLimit-Reset should be a future Unix timestamp."""
    r = client.get("/test")
    reset = int(r.headers["X-RateLimit-Reset"])
    now = int(time.time())
    assert reset >= now
    assert reset <= now + WINDOW_SECONDS + 5