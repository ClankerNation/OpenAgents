"""Tests for the rate limiter middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from middleware.ratelimit import RateLimitMiddleware, RateLimitConfig, _request_counts


@pytest.fixture(autouse=True)
def reset_rate_limits():
    _request_counts.clear()


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    config = RateLimitConfig(
        auth_requests_per_window=5,
        anon_requests_per_window=2,
        window_seconds=60,
        burst_limit=3,
    )
    app.add_middleware(RateLimitMiddleware, config=config)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRateLimit:
    def test_health_route_exempt(self, client):
        for _ in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_anon_rate_limit_exceeded(self, client):
        resp1 = client.get("/test")
        assert resp1.status_code == 200
        assert int(resp1.headers["x-ratelimit-remaining"]) >= 0
        assert resp1.headers["x-ratelimit-bucket"] == "anonymous"

        resp2 = client.get("/test")
        assert resp2.status_code == 200

        resp3 = client.get("/test")
        assert resp3.status_code == 429
        assert "retry_after" in resp3.json()
        assert resp3.json()["bucket"] == "anonymous"

    def test_auth_rate_limit_higher(self, client):
        headers = {"Authorization": "Bearer test-token"}
        for _ in range(5):
            resp = client.get("/test", headers=headers)
            assert resp.status_code == 200
            assert resp.headers["x-ratelimit-bucket"] == "authenticated"

    def test_auth_rate_limit_exceeded(self):
        config = RateLimitConfig(
            auth_requests_per_window=3, anon_requests_per_window=2, window_seconds=60
        )
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        async def ep():
            return {"ok": True}

        c = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}

        for _ in range(3):
            resp = c.get("/test", headers=headers)
            assert resp.status_code == 200

        resp = c.get("/test", headers=headers)
        assert resp.status_code == 429
        assert resp.json()["bucket"] == "authenticated"

    def test_anon_and_auth_separate_buckets(self):
        config = RateLimitConfig(
            auth_requests_per_window=5, anon_requests_per_window=1, window_seconds=60
        )
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        async def ep():
            return {"ok": True}

        c = TestClient(app)
        headers = {"Authorization": "Bearer t"}

        resp1 = c.get("/test")
        assert resp1.status_code == 200
        assert resp1.headers["x-ratelimit-bucket"] == "anonymous"

        resp2 = c.get("/test")
        assert resp2.status_code == 429
        assert resp2.json()["bucket"] == "anonymous"

        resp3 = c.get("/test", headers=headers)
        assert resp3.status_code == 200
        assert resp3.headers["x-ratelimit-bucket"] == "authenticated"

    def test_no_auth_header_treated_as_anon(self):
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(anon_requests_per_window=5, auth_requests_per_window=10),
        )

        @app.get("/test")
        async def ep():
            return {"ok": True}

        c = TestClient(app)
        resp = c.get("/test", headers={"Authorization": ""})
        assert resp.status_code == 200
        assert resp.headers["x-ratelimit-bucket"] == "anonymous"

    def test_window_reset(self, client):
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_x_forwarded_for_used(self, client):
        resp = client.get("/test", headers={"X-Forwarded-For": "1.2.3.4"})
        assert resp.status_code == 200

    def test_create_rate_limiter_helper(self):
        from middleware.ratelimit import create_rate_limiter
        limiter = create_rate_limiter(
            auth_requests_per_minute=300,
            anon_requests_per_minute=30,
            burst=50,
        )
        assert limiter.config.auth_requests_per_window == 300
        assert limiter.config.anon_requests_per_window == 30
        assert limiter.config.burst_limit == 50
        assert limiter.config.window_seconds == 60
