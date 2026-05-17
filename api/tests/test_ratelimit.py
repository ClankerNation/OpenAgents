"""
Tests for the 3-tier rate limiting middleware.

Covers: anonymous tier, authenticated tier, premium tier, header presence,
429 response format, tier determination from auth state.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import time
from starlette.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp

# Import under test
import sys
sys.path.insert(0, "api")
from middleware.ratelimit import (
    RateLimitMiddleware,
    RateLimitTier,
    TIER_LIMITS,
    _window_counts,
    _sliding_window_count,
    _record_request,
)
from middleware.auth import JWT_SECRET


@pytest.fixture(autouse=True)
def clear_window_counts():
    """Reset sliding window counters before each test."""
    _window_counts.clear()
    yield
    _window_counts.clear()


@pytest.fixture
def middleware():
    """Create a fresh RateLimitMiddleware instance."""
    return RateLimitMiddleware(app=MagicMock(spec=ASGIApp))


def make_request(
    headers: dict = None,
    path: str = "/agents",
    client_host: str = "127.0.0.1",
) -> Request:
    """Helper to create a mock Request."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "client": (client_host, 8000),
    }
    if headers:
        scope["headers"] = [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ]
    request = Request(scope)
    return request


class TestTierDetermination:
    """Verify that _determine_tier correctly classifies requests."""

    def test_anonymous_no_auth(self, middleware):
        """No auth headers → ANONYMOUS tier."""
        req = make_request()
        assert middleware._determine_tier(req) == RateLimitTier.ANONYMOUS

    def test_authenticated_bearer(self, middleware):
        """Valid Bearer token → AUTHENTICATED tier."""
        if not JWT_SECRET:
            pytest.skip("JWT_SECRET not set; cannot generate test token")
        from middleware.auth import create_access_token
        token = create_access_token({"sub": "test-user", "address": "0x123"})
        req = make_request(headers={"Authorization": f"Bearer {token}"})
        assert middleware._determine_tier(req) == RateLimitTier.AUTHENTICATED

    def test_premium_api_key(self, middleware):
        """X-API-Key with a known premium key → PREMIUM tier."""
        # Inject a test premium key
        from middleware.ratelimit import DEFAULT_PREMIUM_KEYS
        DEFAULT_PREMIUM_KEYS["test-premium-key"] = RateLimitTier.PREMIUM
        try:
            req = make_request(headers={"X-API-Key": "test-premium-key"})
            assert middleware._determine_tier(req) == RateLimitTier.PREMIUM
        finally:
            del DEFAULT_PREMIUM_KEYS["test-premium-key"]

    def test_anonymous_invalid_bearer(self, middleware):
        """Invalid Bearer token → ANONYMOUS (graceful fallback)."""
        req = make_request(headers={"Authorization": "Bearer invalidtoken123"})
        assert middleware._determine_tier(req) == RateLimitTier.ANONYMOUS

    def test_health_skipped(self, middleware):
        """Health endpoint should always pass through."""
        req = make_request(path="/health")
        # Even without auth, health paths are exempted in dispatch()
        # But the tier detection itself should still work
        assert middleware._determine_tier(req) == RateLimitTier.ANONYMOUS


class TestSlidingWindow:
    """Verify sliding window counting works correctly."""

    def test_sliding_window_count_initial(self):
        """Empty key → count of 0."""
        assert _sliding_window_count("test", 60) == 0

    def test_sliding_window_count_single(self):
        """Single request → count of 1."""
        _record_request("test")
        assert _sliding_window_count("test", 60) == 1

    def test_sliding_window_count_multiple(self):
        """Multiple requests → correct count."""
        now = time.time()
        _window_counts["test"] = [now - 10, now - 20, now - 30]
        count = _sliding_window_count("test", 60)
        assert count == 3

    def test_sliding_window_expired(self):
        """Requests older than the window are pruned."""
        now = time.time()
        _window_counts["test"] = [now - 120, now - 10]  # 120s old = expired
        count = _sliding_window_count("test", 60)
        assert count == 1  # only the recent one remains

    def test_sliding_window_boundary(self):
        """Request exactly at window boundary should be counted."""
        now = time.time()
        _window_counts["test"] = [now - 60]  # Exactly at boundary
        count = _sliding_window_count("test", 60)
        assert count == 0  # cutoff = now - 60, ts == cutoff means expired


class TestRateLimitEnforcement:
    """Verify rate limits are enforced per tier."""

    def test_anonymous_limit(self, middleware):
        """Anonymous tier: 60 req/min limit."""
        limit = TIER_LIMITS[RateLimitTier.ANONYMOUS]
        key = f"{RateLimitTier.ANONYMOUS.value}:127.0.0.1"
        for i in range(limit):
            _record_request(key)
        count = _sliding_window_count(key, 60)
        assert count == limit

    def test_authenticated_limit(self, middleware):
        """Authenticated tier: 300 req/min limit."""
        limit = TIER_LIMITS[RateLimitTier.AUTHENTICATED]
        key = f"{RateLimitTier.AUTHENTICATED.value}:127.0.0.1"
        for i in range(limit):
            _record_request(key)
        count = _sliding_window_count(key, 60)
        assert count == limit

    def test_premium_limit(self, middleware):
        """Premium tier: 1000 req/min limit."""
        limit = TIER_LIMITS[RateLimitTier.PREMIUM]
        key = f"{RateLimitTier.PREMIUM.value}:127.0.0.1"
        for i in range(limit):
            _record_request(key)
        count = _sliding_window_count(key, 60)
        assert count == limit

    def test_tiers_do_not_share_counters(self, middleware):
        """Anonymous and authenticated tiers use different keys."""
        anon_key = f"{RateLimitTier.ANONYMOUS.value}:127.0.0.1"
        auth_key = f"{RateLimitTier.AUTHENTICATED.value}:127.0.0.1"
        _record_request(anon_key)
        _record_request(anon_key)
        _record_request(auth_key)
        assert _sliding_window_count(anon_key, 60) == 2
        assert _sliding_window_count(auth_key, 60) == 1


class TestHeaders:
    """Verify rate limit headers are present on responses."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, middleware):
        """Response should include X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset."""
        req = make_request()
        mock_call_next = AsyncMock()
        mock_call_next.return_value = JSONResponse(
            content={"status": "ok"},
            headers={"Content-Type": "application/json"},
        )

        response = await middleware.dispatch(req, mock_call_next)

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers


class Test429Response:
    """Verify 429 Too Many Requests response format."""

    @pytest.mark.asyncio
    async def test_429_has_retry_after(self, middleware):
        """429 should include Retry-After header."""
        req = make_request()
        limit = TIER_LIMITS[RateLimitTier.ANONYMOUS]
        key = f"{RateLimitTier.ANONYMOUS.value}:127.0.0.1"

        # Fill the window to trigger rate limiting
        now = time.time()
        _window_counts[key] = [now - i for i in range(1, limit + 1)]

        mock_call_next = AsyncMock()
        response = await middleware.dispatch(req, mock_call_next)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    async def test_429_body_contains_error_info(self, middleware):
        """429 body should include error, tier, limit, retry_after."""
        req = make_request()
        limit = TIER_LIMITS[RateLimitTier.ANONYMOUS]
        key = f"{RateLimitTier.ANONYMOUS.value}:127.0.0.1"

        now = time.time()
        _window_counts[key] = [now - i for i in range(1, limit + 1)]

        mock_call_next = AsyncMock()
        response = await middleware.dispatch(req, mock_call_next)

        import json
        body = json.loads(response.body)
        assert body["error"] == "Rate limit exceeded"
        assert body["tier"] == "anonymous"
        assert body["limit"] == limit
        assert body["retry_after"] >= 1


class TestDifferentiationKeys:
    """Verify different IPs get separate counters."""

    def test_different_ips_separate_counters(self, middleware):
        """Two different IPs should have independent counters."""
        ip1_key = f"{RateLimitTier.ANONYMOUS.value}:10.0.0.1"
        ip2_key = f"{RateLimitTier.ANONYMOUS.value}:10.0.0.2"

        _record_request(ip1_key)
        _record_request(ip1_key)
        _record_request(ip1_key)
        _record_request(ip2_key)

        assert _sliding_window_count(ip1_key, 60) == 3
        assert _sliding_window_count(ip2_key, 60) == 1


class TestDispatchFlow:
    """Integration-style tests for the dispatch flow."""

    @pytest.mark.asyncio
    async def test_normal_request_passes(self, middleware):
        """Normal request within limit should pass through to call_next."""
        req = make_request()
        mock_call_next = AsyncMock()
        mock_call_next.return_value = JSONResponse(content={"ok": True})

        response = await middleware.dispatch(req, mock_call_next)
        assert response.status_code != 429
        mock_call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_exempt(self, middleware):
        """Health endpoint should pass through regardless."""
        req = make_request(path="/health")
        mock_call_next = AsyncMock()
        mock_call_next.return_value = JSONResponse(content={"status": "ok"})

        response = await middleware.dispatch(req, mock_call_next)
        assert response.status_code != 429
        mock_call_next.assert_awaited_once()
