"""Tests for the rate-limiter Redis → in-memory fallback behaviour."""

import logging
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from api.middleware.ratelimit import (
    InMemoryRateLimiter,
    RateLimitConfig,
    RateLimitMiddleware,
    RedisRateLimiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app(
    redis_client=None,
    requests_per_window: int = 5,
    window_seconds: int = 60,
) -> FastAPI:
    """Construct a minimal FastAPI app with the rate-limit middleware."""
    test_app = FastAPI()

    config = RateLimitConfig(
        requests_per_window=requests_per_window,
        window_seconds=window_seconds,
    )
    test_app.add_middleware(
        RateLimitMiddleware,
        config=config,
        redis_client=redis_client,
    )

    @test_app.get("/ping")
    async def ping():
        return {"pong": True}

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    return test_app


# ---------------------------------------------------------------------------
# In-memory sliding-window unit tests
# ---------------------------------------------------------------------------

class TestInMemoryRateLimiter:
    """Validate the standalone in-memory sliding-window limiter."""

    def test_allows_requests_within_limit(self):
        config = RateLimitConfig(requests_per_window=3, window_seconds=60)
        limiter = InMemoryRateLimiter(config)

        for _ in range(3):
            limited, _ = limiter.is_rate_limited("10.0.0.1")
            assert not limited

    def test_blocks_after_limit_exceeded(self):
        config = RateLimitConfig(requests_per_window=3, window_seconds=60)
        limiter = InMemoryRateLimiter(config)

        for _ in range(3):
            limiter.is_rate_limited("10.0.0.1")

        limited, retry_after = limiter.is_rate_limited("10.0.0.1")
        assert limited
        assert retry_after >= 1

    def test_remaining_count_decreases(self):
        config = RateLimitConfig(requests_per_window=5, window_seconds=60)
        limiter = InMemoryRateLimiter(config)

        _, remaining = limiter.is_rate_limited("10.0.0.1")
        assert remaining == 4
        _, remaining = limiter.is_rate_limited("10.0.0.1")
        assert remaining == 3

    def test_separate_ips_tracked_independently(self):
        config = RateLimitConfig(requests_per_window=2, window_seconds=60)
        limiter = InMemoryRateLimiter(config)

        limiter.is_rate_limited("10.0.0.1")
        limiter.is_rate_limited("10.0.0.1")
        limited_a, _ = limiter.is_rate_limited("10.0.0.1")
        limited_b, _ = limiter.is_rate_limited("10.0.0.2")

        assert limited_a is True
        assert limited_b is False

    def test_window_expiry_allows_new_requests(self):
        config = RateLimitConfig(requests_per_window=1, window_seconds=1)
        limiter = InMemoryRateLimiter(config)

        limiter.is_rate_limited("10.0.0.1")
        limited, _ = limiter.is_rate_limited("10.0.0.1")
        assert limited

        # Simulate window passage
        time.sleep(1.1)
        limited, _ = limiter.is_rate_limited("10.0.0.1")
        assert not limited

    def test_reset_clears_all_state(self):
        config = RateLimitConfig(requests_per_window=1, window_seconds=60)
        limiter = InMemoryRateLimiter(config)

        limiter.is_rate_limited("10.0.0.1")
        limited, _ = limiter.is_rate_limited("10.0.0.1")
        assert limited

        limiter.reset()
        limited, _ = limiter.is_rate_limited("10.0.0.1")
        assert not limited


# ---------------------------------------------------------------------------
# Redis failure → fallback activation
# ---------------------------------------------------------------------------

class TestRedisFallback:
    """Simulate Redis outages and verify seamless in-memory fallback."""

    def _make_failing_redis(self, error_cls=ConnectionError):
        """Create a mock Redis client whose pipeline always raises."""
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.side_effect = error_cls("Connection refused")
        mock_redis.pipeline.return_value = mock_pipe
        return mock_redis

    def test_connection_error_triggers_fallback(self):
        """A Redis ConnectionError must not crash the request."""
        redis = self._make_failing_redis(ConnectionError)
        app = _build_app(redis_client=redis, requests_per_window=10)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers

    def test_timeout_error_triggers_fallback(self):
        """A Redis TimeoutError must not crash the request."""
        redis = self._make_failing_redis(TimeoutError)
        app = _build_app(redis_client=redis, requests_per_window=10)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_os_error_triggers_fallback(self):
        """An OSError (e.g. socket failure) must not crash the request."""
        redis = self._make_failing_redis(OSError)
        app = _build_app(redis_client=redis, requests_per_window=10)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_unexpected_error_triggers_fallback(self):
        """Any unexpected exception from redis-py must still fall back."""
        redis = self._make_failing_redis(RuntimeError)
        app = _build_app(redis_client=redis, requests_per_window=10)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_fallback_warning_logged(self, caplog):
        """A warning must be emitted when the middleware drops to fallback."""
        redis = self._make_failing_redis(ConnectionError)
        app = _build_app(redis_client=redis, requests_per_window=10)
        client = TestClient(app)

        with caplog.at_level(logging.WARNING, logger="openagents.ratelimit"):
            client.get("/ping")

        assert any("in-memory rate-limit fallback" in m for m in caplog.messages)

    def test_fallback_enforces_limits(self):
        """The in-memory fallback must still enforce rate limits correctly."""
        redis = self._make_failing_redis(ConnectionError)
        app = _build_app(redis_client=redis, requests_per_window=3)
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/ping")
            assert resp.status_code == 200

        resp = client.get("/ping")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == "Rate limit exceeded"
        assert "Retry-After" in resp.headers

    def test_no_500_under_sustained_redis_failure(self):
        """Under continuous Redis failure, no request should ever 500."""
        redis = self._make_failing_redis(ConnectionError)
        app = _build_app(redis_client=redis, requests_per_window=100)
        client = TestClient(app)

        statuses = [client.get("/ping").status_code for _ in range(50)]
        assert 500 not in statuses


# ---------------------------------------------------------------------------
# Middleware integration (no Redis — pure memory mode)
# ---------------------------------------------------------------------------

class TestMiddlewareIntegration:
    """End-to-end middleware tests without any Redis backend."""

    def test_health_endpoint_bypasses_limiter(self):
        app = _build_app(requests_per_window=1)
        client = TestClient(app)

        # /health should never be rate-limited
        for _ in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        app = _build_app(requests_per_window=10)
        client = TestClient(app)

        resp = client.get("/ping")
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "10"

    def test_429_includes_retry_after(self):
        app = _build_app(requests_per_window=2)
        client = TestClient(app)

        client.get("/ping")
        client.get("/ping")
        resp = client.get("/ping")

        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) >= 1

    def test_different_ips_independent(self):
        app = _build_app(requests_per_window=1)
        client = TestClient(app)

        resp1 = client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
        resp2 = client.get("/ping", headers={"X-Forwarded-For": "5.6.7.8"})

        assert resp1.status_code == 200
        assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# Mid-flight Redis failure (starts working, then dies)
# ---------------------------------------------------------------------------

class TestMidFlightRedisFailure:
    """Simulate Redis dropping out after serving initial requests."""

    def test_mid_flight_switch_to_fallback(self, caplog):
        """Redis works for the first request, then fails — no 500s."""
        mock_redis = MagicMock()
        mock_pipe = MagicMock()

        # First call succeeds (count=1, within limit)
        call_count = {"n": 0}

        def _execute_side_effect():
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return [0, True, 1, True]  # zrem, zadd, zcard, expire
            raise ConnectionError("Redis went away")

        mock_pipe.execute.side_effect = _execute_side_effect
        mock_pipe.zremrangebyscore.return_value = mock_pipe
        mock_pipe.zadd.return_value = mock_pipe
        mock_pipe.zcard.return_value = mock_pipe
        mock_pipe.expire.return_value = mock_pipe
        mock_redis.pipeline.return_value = mock_pipe

        app = _build_app(redis_client=mock_redis, requests_per_window=100)
        client = TestClient(app)

        # First request — Redis serves it
        resp1 = client.get("/ping")
        assert resp1.status_code == 200

        # Subsequent requests — Redis fails, fallback takes over
        with caplog.at_level(logging.WARNING, logger="openagents.ratelimit"):
            resp2 = client.get("/ping")
            assert resp2.status_code == 200

        assert any("in-memory rate-limit fallback" in m for m in caplog.messages)
