"""Tests for tiered rate limiting middleware.

Covers acceptance criteria:
  - Three tier limits enforced (anonymous 60/min, authenticated 300/min,
    premium 1000/min)
  - Rate limit headers in every response
  - 429 includes Retry-After header
  - Tier determined from request auth state
"""

import time
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Import the module under test (adjust path for local execution)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitTier,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
    _request_windows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app(anon_limit=3, auth_limit=5, premium_limit=10):
    """Build a minimal FastAPI app with tiered rate limiting."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        anonymous_tier=RateLimitTier(anon_limit, window_seconds=60),
        auth_tier=RateLimitTier(auth_limit, window_seconds=60),
        premium_tier=RateLimitTier(premium_limit, window_seconds=60),
    )

    @app.get("/ok")
    async def ok_endpoint(request: Request):
        return {"status": "ok"}

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    return app


def _auth_header(payload: dict) -> str:
    """Build a Bearer token with a minimal JWT-like structure.

    Since the middleware uses jwt.decode with verify_signature=False, any
    structurally-valid JWT string is sufficient for tier detection.
    """
    import base64
    import json

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")
    return f"Bearer {header}.{body}.fake_signature"


# ---------------------------------------------------------------------------
# Clean slate between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_windows():
    _request_windows.clear()
    yield
    _request_windows.clear()


# ---------------------------------------------------------------------------
# Anonymous tier
# ---------------------------------------------------------------------------

class TestAnonymousTier:
    def test_anon_gets_headers(self):
        client = TestClient(_build_app(anon_limit=60))
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers
        assert resp.headers["x-ratelimit-limit"] == "60"

    def test_anon_hits_limit_then_429(self):
        limit = 3
        client = TestClient(_build_app(anon_limit=limit))
        for i in range(limit):
            resp = client.get("/ok")
            assert resp.status_code == 200, f"request {i+1} should pass"

        resp = client.get("/ok")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        data = resp.json()
        assert "error" in data
        assert "retry_after" in data
        assert data["tier"] == "anonymous"


# ---------------------------------------------------------------------------
# Authenticated tier
# ---------------------------------------------------------------------------

class TestAuthenticatedTier:
    def test_auth_gets_higher_limit(self):
        limit = 5
        client = TestClient(_build_app(auth_limit=limit))
        headers = {"Authorization": _auth_header({"roles": []})}
        for i in range(limit):
            resp = client.get("/ok", headers=headers)
            assert resp.status_code == 200, f"request {i+1} should pass"
        resp = client.get("/ok", headers=headers)
        assert resp.status_code == 429

    def test_auth_headers_present(self):
        client = TestClient(_build_app(auth_limit=300))
        headers = {"Authorization": _auth_header({"roles": []})}
        resp = client.get("/ok", headers=headers)
        assert resp.status_code == 200
        assert resp.headers["x-ratelimit-limit"] == "300"


# ---------------------------------------------------------------------------
# Premium tier
# ---------------------------------------------------------------------------

class TestPremiumTier:
    def test_premium_gets_highest_limit(self):
        limit = 10
        client = TestClient(_build_app(premium_limit=limit))
        headers = {"Authorization": _auth_header({"roles": ["premium"]})}
        for i in range(limit):
            resp = client.get("/ok", headers=headers)
            assert resp.status_code == 200, f"request {i+1} should pass"
        resp = client.get("/ok", headers=headers)
        assert resp.status_code == 429

    def test_premium_tier_label_in_429(self):
        limit = 2
        client = TestClient(_build_app(premium_limit=limit))
        headers = {"Authorization": _auth_header({"roles": ["premium"]})}
        for _ in range(limit):
            client.get("/ok", headers=headers)
        resp = client.get("/ok", headers=headers)
        assert resp.status_code == 429
        assert resp.json()["tier"] == "premium"


# ---------------------------------------------------------------------------
# Tier isolation
# ---------------------------------------------------------------------------

class TestTierIsolation:
    def test_anon_and_auth_independent(self):
        """Anonymous limit exhaustion does not affect authenticated users."""
        client = TestClient(_build_app(anon_limit=2, auth_limit=10))
        # Exhaust anonymous
        for _ in range(2):
            client.get("/ok")
        assert client.get("/ok").status_code == 429
        # Authenticated still works
        headers = {"Authorization": _auth_header({"roles": []})}
        resp = client.get("/ok", headers=headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Health endpoint bypass
# ---------------------------------------------------------------------------

class TestHealthBypass:
    def test_health_not_rate_limited(self):
        client = TestClient(_build_app(anon_limit=1))
        # Exhaust limit
        client.get("/ok")
        assert client.get("/ok").status_code == 429
        # Health still passes
        resp = client.get("/health")
        assert resp.status_code == 200
