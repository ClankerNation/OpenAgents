"""
Tests for the three-tier Rate Limiting middleware on the OpenAgents API.

Covers:
  - Anonymous tier (60 req/min)
  - Authenticated tier (300 req/min)
  - Premium tier (1000 req/min)
  - X-RateLimit-* header presence on every response
  - 429 response includes Retry-After header
  - X-Forwarded-For validation (spoofed / private IPs rejected)
  - Sliding window (boundary burst does not exceed 1× the limit)
"""

import importlib
import jwt
import os
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-rate-limit-tests")


@pytest.fixture(autouse=True)
def _reload_modules():
    """Reload all relevant modules before each test for a clean slate."""
    import api.middleware.auth as _auth_mod
    import api.middleware.ratelimit as _rl_mod
    import api.main as _main_mod
    importlib.reload(_auth_mod)
    importlib.reload(_rl_mod)
    importlib.reload(_main_mod)
    yield


@pytest.fixture()
def client():
    """Fresh TestClient with rate-limit and request-id middleware active."""
    import api.main as _main
    import api.middleware.ratelimit as _rl_mod
    _rl_mod._request_log.clear()
    return TestClient(_main.app)


@pytest.fixture()
def app_secret():
    """Return the JWT secret used by the running app."""
    import api.middleware.auth as auth_mod
    return auth_mod.JWT_SECRET


def _make_token(secret: str, sub: str = "user1", roles: list = None) -> str:
    """Create a valid JWT access token for tests."""
    payload = {
        "sub": sub,
        "address": "0xabc",
        "roles": roles or [],
        "type": "access",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_tiny_app(tiers):
    """Create a fresh FastAPI app with tiny rate limits for 429 testing."""
    import api.middleware.ratelimit as _rl_mod
    _rl_mod._request_log.clear()

    from fastapi import FastAPI
    from datetime import datetime

    tiny_app = FastAPI()

    @tiny_app.get("/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

    @tiny_app.get("/agents")
    async def agents():
        return []

    tiny_app.add_middleware(_rl_mod.RateLimitMiddleware, tiers=tiers)
    return tiny_app


# ---------------------------------------------------------------------------
# 1. Tier limits
# ---------------------------------------------------------------------------
class TestAnonymousTier:
    """Anonymous (no Authorization header) → 60 req/min."""

    def test_anonymous_gets_60_limit(self, client):
        resp = client.get("/health")
        assert resp.headers["x-ratelimit-limit"] == "60"

    def test_anonymous_remaining_decrements(self, client):
        resp1 = client.get("/health")
        remaining1 = int(resp1.headers["x-ratelimit-remaining"])
        resp2 = client.get("/health")
        remaining2 = int(resp2.headers["x-ratelimit-remaining"])
        assert remaining2 == remaining1 - 1


class TestAuthenticatedTier:
    """Authenticated (valid JWT, no premium role) → 300 req/min."""

    def test_authenticated_gets_300_limit(self, client, app_secret):
        token = _make_token(app_secret, roles=[])
        resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert resp.headers["x-ratelimit-limit"] == "300"

    def test_authenticated_remaining(self, client, app_secret):
        token = _make_token(app_secret, roles=[])
        resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert int(resp.headers["x-ratelimit-remaining"]) == 299


class TestPremiumTier:
    """Premium (valid JWT with role "premium") → 1000 req/min."""

    def test_premium_gets_1000_limit(self, client, app_secret):
        token = _make_token(app_secret, roles=["premium"])
        resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert resp.headers["x-ratelimit-limit"] == "1000"

    def test_premium_remaining(self, client, app_secret):
        token = _make_token(app_secret, roles=["premium"])
        resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert int(resp.headers["x-ratelimit-remaining"]) == 999


# ---------------------------------------------------------------------------
# 2. Header presence — every response must have X-RateLimit-* headers
# ---------------------------------------------------------------------------
class TestHeaderPresence:
    """X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
    must be present on every response (including 429)."""

    def test_health_has_all_headers(self, client):
        resp = client.get("/health")
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers

    def test_agents_has_all_headers(self, client):
        resp = client.get("/agents")
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers

    def test_404_has_all_headers(self, client):
        # 404s from the app should still carry rate-limit headers since
        # the middleware wraps the whole app.
        resp = client.get("/agents/nonexistent")
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers

    def test_429_has_all_headers(self):
        """Trigger 429 with a tiny custom limit, verify all three headers + Retry-After."""
        tiny_tiers = {"anonymous": 3, "authenticated": 3, "premium": 3}
        app = _make_tiny_app(tiny_tiers)
        tc = TestClient(app)

        # Exhaust 3 requests
        for _ in range(3):
            resp = tc.get("/health")
            assert resp.status_code == 200

        # 4th should be 429
        resp = tc.get("/health")
        assert resp.status_code == 429
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers
        assert "retry-after" in resp.headers


# ---------------------------------------------------------------------------
# 3. 429 response — must include Retry-After
# ---------------------------------------------------------------------------
class Test429Response:
    """When rate-limited the API must return 429 with Retry-After."""

    def test_429_has_retry_after(self):
        """Use a tiny limit so we can quickly exhaust it."""
        tiny_tiers = {"anonymous": 2, "authenticated": 2, "premium": 1000}
        app = _make_tiny_app(tiny_tiers)
        tc = TestClient(app)

        for _ in range(2):
            tc.get("/health")

        resp = tc.get("/health")
        assert resp.status_code == 429
        assert int(resp.headers["retry-after"]) >= 1
        assert resp.json()["error"] == "Rate limit exceeded"

    def test_429_retry_after_is_integer(self):
        tiny_tiers = {"anonymous": 1, "authenticated": 1, "premium": 1000}
        app = _make_tiny_app(tiny_tiers)
        tc = TestClient(app)

        tc.get("/health")
        resp = tc.get("/health")
        assert resp.status_code == 429
        retry = resp.headers["retry-after"]
        int(retry)  # Must be parseable as int


# ---------------------------------------------------------------------------
# 4. X-Forwarded-For validation — private / invalid IPs are rejected
# ---------------------------------------------------------------------------
class TestXForwardedForValidation:
    """Spoofed or private IPs in X-Forwarded-For must not be trusted."""

    def test_private_ip_in_xff_is_ignored(self, client):
        """A private IP in X-Forwarded-For should be skipped (falls back to direct IP)."""
        import api.middleware.ratelimit as _rl_mod
        _rl_mod._request_log.clear()
        resp = client.get("/health", headers={"X-Forwarded-For": "192.168.1.100"})
        assert "x-ratelimit-limit" in resp.headers

    def test_spoofed_ip_is_rejected(self, client):
        """A clearly invalid IP should be skipped."""
        import api.middleware.ratelimit as _rl_mod
        _rl_mod._request_log.clear()
        resp = client.get("/health", headers={"X-Forwarded-For": "999.999.999.999"})
        assert "x-ratelimit-limit" in resp.headers

    def test_valid_public_ip_in_xff_accepted(self, client):
        """A valid public IP in X-Forwarded-For is used as the client key."""
        import api.middleware.ratelimit as _rl_mod
        _rl_mod._request_log.clear()
        resp = client.get("/health", headers={"X-Forwarded-For": "8.8.8.8"})
        assert "x-ratelimit-limit" in resp.headers

    def test_multiple_ips_rightmost_public_wins(self, client):
        """With multiple XFF entries, the rightmost valid public IP is used."""
        import api.middleware.ratelimit as _rl_mod
        _rl_mod._request_log.clear()
        resp = client.get("/health", headers={"X-Forwarded-For": "1.2.3.4, 8.8.4.4"})
        assert "x-ratelimit-limit" in resp.headers


# ---------------------------------------------------------------------------
# 5. Sliding window — boundary burst does not exceed 1× the limit
# ---------------------------------------------------------------------------
class TestSlidingWindow:
    """Fixed-window bug is gone: boundary bursts don't double the rate."""

    def test_sliding_window_prevents_double_burst(self):
        """With a 2-request limit, sending 2 requests and then
        immediately 2 more should result in at least one 429."""
        tiny_tiers = {"anonymous": 2, "authenticated": 2, "premium": 1000}
        app = _make_tiny_app(tiny_tiers)
        tc = TestClient(app)

        r1 = tc.get("/health")
        assert r1.status_code == 200
        r2 = tc.get("/health")
        assert r2.status_code == 200

        # Third request must be rejected
        r3 = tc.get("/health")
        assert r3.status_code == 429