from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


def build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(
            requests_per_window=2,
            authenticated_requests_per_window=3,
            premium_requests_per_window=4,
            window_seconds=60,
        ),
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


def setup_function() -> None:
    _request_counts.clear()


def test_anonymous_limit_and_headers():
    client = build_client()

    r1 = client.get("/ping")
    assert r1.status_code == 200
    assert r1.headers["X-RateLimit-Limit"] == "2"
    assert r1.headers["X-RateLimit-Remaining"] == "1"
    assert "X-RateLimit-Reset" in r1.headers

    r2 = client.get("/ping")
    assert r2.status_code == 200
    assert r2.headers["X-RateLimit-Remaining"] == "0"

    r3 = client.get("/ping")
    assert r3.status_code == 429
    assert r3.headers["X-RateLimit-Limit"] == "2"
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in r3.headers
    assert "Retry-After" in r3.headers


def test_authenticated_limit_is_separate_from_anonymous():
    client = build_client()
    headers = {"Authorization": "Bearer user-token"}

    for _ in range(3):
        response = client.get("/ping", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "3"

    limited = client.get("/ping", headers=headers)
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_premium_api_key_gets_highest_limit():
    client = build_client()
    headers = {"X-API-Key": "premium-key", "X-API-Key-Tier": "premium"}

    for _ in range(4):
        response = client.get("/ping", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "4"

    limited = client.get("/ping", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["X-RateLimit-Limit"] == "4"
    assert "Retry-After" in limited.headers
