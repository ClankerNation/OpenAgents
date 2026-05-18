"""Tests for the rate limiting middleware."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import JSONResponse

from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


@pytest.fixture(autouse=True)
def reset_counts():
    """Reset global request counts before each test."""
    _request_counts.clear()
    yield
    _request_counts.clear()


@pytest.fixture
def config():
    return RateLimitConfig(
        requests_per_window=100,
        window_seconds=60,
        burst_limit=20,
        authenticated_requests_per_window=300,
        anonymous_requests_per_window=60,
        premium_requests_per_window=1000,
    )


def make_mock_request(headers: dict = None, client_host: str = "127.0.0.1"):
    """Helper to create a mock FastAPI Request."""
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/agents",
        "headers": [(k.lower().encode(), str(v).encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 8000),
    }
    req = Request(scope)
    return req


class TestRateLimitConfig:
    def test_default_config(self):
        """Default config uses configured defaults: anon=60, auth=300, premium=1000."""
        cfg = RateLimitConfig()
        assert cfg.requests_per_window == 100
        # Defaults are the constructor defaults (not requests_per_window fallback)
        assert cfg.anonymous_requests_per_window == 60
        assert cfg.authenticated_requests_per_window == 300
        assert cfg.premium_requests_per_window == 1000

    def test_three_tier_config(self):
        """Three-tier limits are enforced when configured."""
        cfg = RateLimitConfig(
            anonymous_requests_per_window=60,
            authenticated_requests_per_window=300,
            premium_requests_per_window=1000,
        )
        assert cfg.limit_for("anonymous") == 60
        assert cfg.limit_for("authenticated") == 300
        assert cfg.limit_for("premium") == 1000

    def test_backward_compatible(self):
        """Backward compatible: when tier knobs are None, falls back to requests_per_window."""
        cfg = RateLimitConfig(
            requests_per_window=100,
            authenticated_requests_per_window=None,
            anonymous_requests_per_window=None,
            premium_requests_per_window=None,
        )
        assert cfg.authenticated_requests_per_window == 100
        assert cfg.anonymous_requests_per_window == 100
        assert cfg.premium_requests_per_window == 100

    def test_premium_falls_back_to_authenticated(self):
        """Premium falls back to authenticated when unset."""
        cfg = RateLimitConfig(
            authenticated_requests_per_window=300,
            premium_requests_per_window=None,
        )
        assert cfg.premium_requests_per_window == 300

    def test_bucket_format(self, config):
        """Bucket key combines tier and IP."""
        assert config.bucket_for("1.2.3.4", "anonymous") == "anonymous:1.2.3.4"
        assert config.bucket_for("5.6.7.8", "premium") == "premium:5.6.7.8"


class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_anonymous_rate_limit(self, config):
        """Anonymous tier gets 60 req/min limit."""
        middleware = RateLimitMiddleware(app=None, config=config)
        is_limited, remaining, reset_at = middleware._is_rate_limited("1.2.3.4", "anonymous")
        assert not is_limited
        assert remaining == 59  # 60 - 1

    @pytest.mark.asyncio
    async def test_authenticated_rate_limit(self, config):
        """Authenticated tier gets 300 req/min limit."""
        middleware = RateLimitMiddleware(app=None, config=config)
        is_limited, remaining, reset_at = middleware._is_rate_limited("1.2.3.4", "authenticated")
        assert not is_limited
        assert remaining == 299  # 300 - 1

    @pytest.mark.asyncio
    async def test_premium_rate_limit(self, config):
        """Premium tier gets 1000 req/min limit."""
        middleware = RateLimitMiddleware(app=None, config=config)
        is_limited, remaining, reset_at = middleware._is_rate_limited("1.2.3.4", "premium")
        assert not is_limited
        assert remaining == 999  # 1000 - 1

    @pytest.mark.asyncio
    async def test_anonymous_exhaustion(self, config):
        """Anonymous requests are limited after 60 requests."""
        middleware = RateLimitMiddleware(app=None, config=config)
        now = time.time()

        # Fill bucket with 60 requests at current time
        _request_counts["anonymous:1.2.3.4"] = (60, now)

        is_limited, retry_after, reset_at = middleware._is_rate_limited("1.2.3.4", "anonymous")
        assert is_limited
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_tier_detection_anonymous(self, config):
        """Request without auth headers is detected as anonymous."""
        middleware = RateLimitMiddleware(app=None, config=config)
        req = make_mock_request(headers={})
        tier = middleware._get_tier(req)
        assert tier == "anonymous"

    @pytest.mark.asyncio
    async def test_tier_detection_authenticated(self, config):
        """Request with Authorization header is authenticated."""
        middleware = RateLimitMiddleware(app=None, config=config)
        req = make_mock_request(headers={"Authorization": "Bearer test-token"})
        tier = middleware._get_tier(req)
        assert tier == "authenticated"

    @pytest.mark.asyncio
    async def test_tier_detection_premium(self, config):
        """Request with premium API key is premium."""
        middleware = RateLimitMiddleware(app=None, config=config)
        req = make_mock_request(headers={"X-Api-Key": "sk-abc123:premium"})
        tier = middleware._get_tier(req)
        assert tier == "premium"

    @pytest.mark.asyncio
    async def test_429_response_headers(self, config):
        """429 response includes Retry-After, X-RateLimit-* headers."""
        middleware = RateLimitMiddleware(app=None, config=config)
        now = time.time()
        _request_counts["anonymous:127.0.0.1"] = (60, now)

        mock_call_next = AsyncMock(return_value=JSONResponse(content={}))

        req = make_mock_request(headers={})
        response = await middleware.dispatch(req, mock_call_next)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "60"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"].isdigit()

    @pytest.mark.asyncio
    async def test_success_response_headers(self, config):
        """Normal response includes X-RateLimit-* headers."""
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_call_next = AsyncMock(return_value=JSONResponse(content={"status": "ok"}))

        req = make_mock_request(headers={})
        response = await middleware.dispatch(req, mock_call_next)

        assert response.status_code != 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "60"

    @pytest.mark.asyncio
    async def test_health_path_skipped(self, config):
        """Health endpoint is not rate limited."""
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_call_next = AsyncMock(return_value=JSONResponse(content={"status": "healthy"}))

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "client": ("127.0.0.1", 8000),
        }
        req = Request(scope)
        response = await middleware.dispatch(req, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_awaited_once()


class TestTierSeparation:
    @pytest.mark.asyncio
    async def test_anonymous_and_authenticated_separate(self, config):
        """Anonymous and authenticated clients have independent rate limits."""
        middleware = RateLimitMiddleware(app=None, config=config)
        now = time.time()

        # Exhaust anonymous limit for this IP
        client_ip = "10.0.0.1"
        _request_counts[f"anonymous:{client_ip}"] = (60, now)

        # Anonymous should be limited
        anon_limited, _, _ = middleware._is_rate_limited(client_ip, "anonymous")
        assert anon_limited, "Anonymous should be rate limited after 60 requests"

        # Authenticated should NOT be limited (separate bucket)
        auth_limited, remaining, _ = middleware._is_rate_limited(client_ip, "authenticated")
        assert not auth_limited, "Authenticated should not be rate limited"
        assert remaining == 299

    @pytest.mark.asyncio
    async def test_premium_separate_from_authenticated(self, config):
        """Premium and authenticated clients have independent rate limits."""
        middleware = RateLimitMiddleware(app=None, config=config)
        now = time.time()

        client_ip = "10.0.0.2"

        # Exhaust authenticated limit
        _request_counts[f"authenticated:{client_ip}"] = (300, now)

        auth_limited, _, _ = middleware._is_rate_limited(client_ip, "authenticated")
        assert auth_limited, "Authenticated should be rate limited after 300 requests"

        # Premium should NOT be limited
        premium_limited, remaining, _ = middleware._is_rate_limited(client_ip, "premium")
        assert not premium_limited, "Premium should not be rate limited"
        assert remaining == 999
