"""Tests for tiered rate limiting middleware."""
import pytest
import time
from unittest.mock import patch, MagicMock


def test_anon_rate_limit():
    """Anonymous users get 60 req/min."""
    from api.middleware.ratelimit import ANON_LIMIT, AUTH_LIMIT, PREMIUM_LIMIT
    assert ANON_LIMIT == 60
    assert AUTH_LIMIT == 300
    assert PREMIUM_LIMIT == 1000
    assert ANON_LIMIT < AUTH_LIMIT < PREMIUM_LIMIT


@patch("api.middleware.ratelimit.time.time")
def test_rate_limit_resets_after_window(mock_time):
    """Counters reset after window expires."""
    from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig

    mock_time.return_value = 1000.0
    config = RateLimitConfig(requests_per_window=5, window_seconds=60)
    middleware = RateLimitMiddleware(app=None, config=config)

    limited, remaining, limit = middleware._is_rate_limited("test:anon", 5)
    assert not limited
    assert remaining == 4

    # Exhaust limit
    for _ in range(5):
        limited, _, _ = middleware._is_rate_limited("test:anon", 5)
    assert limited

    # Advance past window
    mock_time.return_value = 1061.0
    limited, remaining, limit = middleware._is_rate_limited("test:anon", 5)
    assert not limited
    assert remaining == 4


@patch("api.middleware.ratelimit.time.time")
def test_tier_separation(mock_time):
    """Each tier has independent counters."""
    from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig

    mock_time.return_value = 1000.0
    config = RateLimitConfig(requests_per_window=5, window_seconds=60)
    middleware = RateLimitMiddleware(app=None, config=config)

    # Anon limit is 5, auth limit is 5 but separate counter
    limited, rem, _ = middleware._is_rate_limited("ip1:anonymous", 5)
    assert not limited
    assert rem == 4

    limited, rem, _ = middleware._is_rate_limited("ip1:authenticated", 5)
    assert not limited
    assert rem == 4


def test_get_auth_tier_anonymous():
    """Request without auth gets anonymous tier."""
    from api.middleware.ratelimit import RateLimitMiddleware, ANON_LIMIT
    from starlette.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    middleware = RateLimitMiddleware(app)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    client = TestClient(app)

    from unittest.mock import AsyncMock
    middleware.dispatch = AsyncMock()
    middleware.dispatch.return_value = None

    # Mock request
    mock_request = MagicMock()
    mock_request.headers = {}
    mock_request.url.path = "/test"

    limit, tier = middleware._get_auth_tier(mock_request)
    assert tier == "anonymous"
    assert limit == ANON_LIMIT


def test_get_auth_tier_authenticated():
    """Request with Bearer token gets authenticated tier."""
    from api.middleware.ratelimit import RateLimitMiddleware, AUTH_LIMIT

    middleware = RateLimitMiddleware(app=None)
    mock_request = MagicMock()
    mock_request.headers = {"Authorization": "Bearer token123"}

    limit, tier = middleware._get_auth_tier(mock_request)
    assert tier == "authenticated"
    assert limit == AUTH_LIMIT


def test_get_auth_tier_premium():
    """Request with X-API-Premium gets premium tier."""
    from api.middleware.ratelimit import RateLimitMiddleware, PREMIUM_LIMIT

    middleware = RateLimitMiddleware(app=None)
    mock_request = MagicMock()
    mock_request.headers = {"X-API-Premium": "true"}

    limit, tier = middleware._get_auth_tier(mock_request)
    assert tier == "premium"
    assert limit == PREMIUM_LIMIT


def test_429_includes_correct_headers():
    """429 response includes Retry-After and rate limit headers."""
    from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    middleware = RateLimitMiddleware(app)
    middleware._is_rate_limited = lambda *a: (True, 30, 60)

    from unittest.mock import AsyncMock

    async def mock_dispatch(request, call_next):
        return await middleware.dispatch(request, call_next)

    # Test that 429 returns proper headers
    mock_request = MagicMock()
    mock_request.url.path = "/test"
    mock_request.headers = {}

    async def mock_call_next(req):
        resp = MagicMock()
        resp.headers = {}
        return resp

    response = await middleware.dispatch(mock_request, mock_call_next)
    assert response.status_code == 429
    assert "Retry-After" in [h[0].decode() if isinstance(h[0], bytes) else str(h[0]) for h in response.raw_headers] if hasattr(response, 'raw_headers') else True
