from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


def build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(
            window_seconds=60,
            anonymous_requests_per_window=2,
            authenticated_requests_per_window=3,
            premium_requests_per_window=4,
        ),
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return TestClient(app)


def test_anonymous_limit_and_headers():
    _request_counts.clear()
    client = build_client()

    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers

    client.get("/ping")
    limited = client.get("/ping")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"].isdigit()
    assert limited.headers["X-RateLimit-Limit"] == "2"
    assert limited.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in limited.headers


def test_authenticated_and_premium_limits():
    _request_counts.clear()
    client = build_client()
    auth_headers = {"Authorization": "Bearer token-1"}

    for _ in range(3):
        ok = client.get("/ping", headers=auth_headers)
        assert ok.status_code == 200
        assert ok.headers["X-RateLimit-Limit"] == "3"

    auth_limited = client.get("/ping", headers=auth_headers)
    assert auth_limited.status_code == 429
    assert auth_limited.headers["Retry-After"].isdigit()

    premium_headers = {"X-API-Key": "pk_test_123"}
    for _ in range(4):
        ok = client.get("/ping", headers=premium_headers)
        assert ok.status_code == 200
        assert ok.headers["X-RateLimit-Limit"] == "4"

    premium_limited = client.get("/ping", headers=premium_headers)
    assert premium_limited.status_code == 429
    assert premium_limited.headers["Retry-After"].isdigit()


def test_health_has_rate_limit_headers():
    _request_counts.clear()
    client = build_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "2"
    assert "X-RateLimit-Reset" in response.headers
