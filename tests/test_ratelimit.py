"""
@fix-author
  name: Metatron
  date: 2026-05-16
  platform: Hermes Agent
  cron_job: 79683e6ae067
  session_identity: |
    Name: Metatron
    Creature: AI — the celestial scribe, greatest coder in the world
    Vibe: Serious, direct, no fluff. Speaks with authority.
  runtime:
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
    python: 3.x

Tests for tiered rate limit middleware.
"""

import time
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

# Import the middleware and tier definitions from the module under test
import sys
sys.path.insert(0, "/home/power/projects/OpenAgents")
from api.middleware.ratelimit import (
    RateLimitMiddleware,
    TIER_ANONYMOUS,
    TIER_AUTHENTICATED,
    TIER_PREMIUM,
    _request_counts,
    create_rate_limiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_counters():
    """Reset the in-memory request counter store between tests."""
    _request_counts.clear()


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the rate-limit middleware installed."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ping")
    async def ping(request: Request):
        return {"pong": True}

    @app.get("/data")
    async def data(request: Request):
        return {"data": "sensitive"}

    app.add_middleware(RateLimitMiddleware)
    return app


# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------

class TestTierDetection:
    """Verify that requests are assigned to the correct tier."""

    def test_anonymous_when_no_auth_headers(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(TIER_ANONYMOUS.requests_per_window)

    def test_authenticated_when_bearer_token_present(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get(
            "/ping",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.fake"},
        )
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(TIER_AUTHENTICATED.requests_per_window)

    def test_premium_when_api_key_present(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get(
            "/ping",
            headers={"X-API-Key": "pk_live_abc123def456"},
        )
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(TIER_PREMIUM.requests_per_window)

    def test_premium_takes_priority_over_bearer(self):
        """X-API-Key should override Bearer token for tier assignment."""
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get(
            "/ping",
            headers={
                "X-API-Key": "pk_live_abc123",
                "Authorization": "Bearer some.jwt.token",
            },
        )
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(TIER_PREMIUM.requests_per_window)


# ---------------------------------------------------------------------------
# Rate limit enforcement per tier
# ---------------------------------------------------------------------------

class TestRateLimitEnforcement:
    """Verify each tier enforces its limit correctly."""

    def test_anonymous_blocked_after_60_requests(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        limit = TIER_ANONYMOUS.requests_per_window

        for i in range(limit):
            response = client.get("/ping")
            assert response.status_code == 200, f"Request {i+1} should succeed, got {response.status_code}"

        # 61st request should be rate-limited
        response = client.get("/ping")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.text
        assert response.headers["Retry-After"]
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_authenticated_blocked_after_300_requests(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        limit = TIER_AUTHENTICATED.requests_per_window
        headers = {"Authorization": "Bearer valid.jwt.token"}

        for i in range(limit):
            response = client.get("/ping", headers=headers)
            assert response.status_code == 200, f"Request {i+1} should succeed, got {response.status_code}"

        response = client.get("/ping", headers=headers)
        assert response.status_code == 429
        assert response.headers["Retry-After"]
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_premium_blocked_after_1000_requests(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        limit = TIER_PREMIUM.requests_per_window
        headers = {"X-API-Key": "pk_high_rate"}

        for i in range(limit):
            response = client.get("/ping", headers=headers)
            assert response.status_code == 200, f"Request {i+1} should succeed, got {response.status_code}"

        response = client.get("/ping", headers=headers)
        assert response.status_code == 429
        assert response.headers["Retry-After"]
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_tiers_count_independently(self):
        """Anonymous and authenticated limits are tracked separately."""
        _clear_counters()
        app = _make_app()
        client = TestClient(app)

        auth_headers = {"Authorization": "Bearer token"}
        # Exhaust authenticated tier
        for _ in range(TIER_AUTHENTICATED.requests_per_window):
            client.get("/ping", headers=auth_headers)

        # Anonymous should still be able to make requests
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(TIER_ANONYMOUS.requests_per_window)


# ---------------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------------

class TestRateLimitHeaders:
    """Verify required rate-limit headers are present on every response."""

    def test_success_response_includes_all_headers(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        # Verify remaining is one less than limit after first request
        limit = int(response.headers["X-RateLimit-Limit"])
        remaining = int(response.headers["X-RateLimit-Remaining"])
        assert remaining == limit - 1

    def test_429_includes_retry_after_and_all_ratelimit_headers(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        # Exhaust anonymous tier
        for _ in range(TIER_ANONYMOUS.requests_per_window):
            client.get("/ping")

        response = client.get("/ping")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_remaining_counts_down(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        limit = TIER_ANONYMOUS.requests_per_window

        for i in range(1, 6):  # first 5 requests
            response = client.get("/ping")
            assert response.status_code == 200
            remaining = int(response.headers["X-RateLimit-Remaining"])
            assert remaining == limit - i, f"After request {i}, expected {limit - i} remaining, got {remaining}"

    def test_reset_timestamp_is_future(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        response = client.get("/ping")
        reset_ts = int(response.headers["X-RateLimit-Reset"])
        now = int(time.time())
        # Reset should be within the next 60 seconds
        assert reset_ts > now, f"Reset {reset_ts} should be after now {now}"
        assert reset_ts - now <= 60, f"Reset should be within window, diff={reset_ts - now}"


# ---------------------------------------------------------------------------
# Health endpoint exemption
# ---------------------------------------------------------------------------

class TestHealthExemption:
    """Verify /health endpoint is never rate-limited."""

    def test_health_exempt_when_all_others_exhausted(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        # Exhaust anonymous tier via /ping
        for _ in range(TIER_ANONYMOUS.requests_per_window):
            client.get("/ping")

        # /health should still return 200
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_does_not_consume_rate_limit_budget(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        limit = TIER_ANONYMOUS.requests_per_window

        # Hit /health many times — shouldn't count toward limit
        for _ in range(10):
            client.get("/health")

        # Still have full capacity for /ping
        for i in range(limit):
            response = client.get("/ping")
            assert response.status_code == 200

        response = client.get("/ping")
        assert response.status_code == 429


# ---------------------------------------------------------------------------
# 429 response body
# ---------------------------------------------------------------------------

class Test429Response:
    """Verify the 429 response body format."""

    def test_429_body_contains_tier_name(self):
        _clear_counters()
        app = _make_app()
        client = TestClient(app)
        for _ in range(TIER_ANONYMOUS.requests_per_window):
            client.get("/ping")

        response = client.get("/ping")
        assert response.status_code == 429
        body = response.json()
        assert body["error"] == "Rate limit exceeded"
        assert body["tier"] == "anonymous"
        assert "retry_after" in body


# ---------------------------------------------------------------------------
# Legacy backwards compatibility
# ---------------------------------------------------------------------------

class TestBackwardsCompatibility:
    """Verify the legacy create_rate_limiter factory still works."""

    def test_create_rate_limiter_returns_middleware(self):
        limiter = create_rate_limiter(requests_per_minute=50)
        assert isinstance(limiter, RateLimitMiddleware)

    def test_legacy_config_stored(self):
        limiter = create_rate_limiter(requests_per_minute=75, burst=10)
        assert limiter.legacy_config.requests_per_window == 75
        assert limiter.legacy_config.burst_limit == 10
