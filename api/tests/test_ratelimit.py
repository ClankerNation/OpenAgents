from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import Optional

from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


def build_client(config: Optional[RateLimitConfig] = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


def test_headers_present_for_all_tiers():
    _request_counts.clear()
    client = build_client()

    anonymous_response = client.get("/ping")
    assert anonymous_response.status_code == 200
    assert anonymous_response.headers["X-RateLimit-Limit"] == "60"
    assert "X-RateLimit-Remaining" in anonymous_response.headers
    assert "X-RateLimit-Reset" in anonymous_response.headers

    authenticated_response = client.get("/ping", headers={"Authorization": "Bearer user-token"})
    assert authenticated_response.status_code == 200
    assert authenticated_response.headers["X-RateLimit-Limit"] == "300"
    assert "X-RateLimit-Remaining" in authenticated_response.headers
    assert "X-RateLimit-Reset" in authenticated_response.headers

    premium_response = client.get("/ping", headers={"X-API-Key": "premium_test_key"})
    assert premium_response.status_code == 200
    assert premium_response.headers["X-RateLimit-Limit"] == "1000"
    assert "X-RateLimit-Remaining" in premium_response.headers
    assert "X-RateLimit-Reset" in premium_response.headers


def test_limits_and_429_retry_after_per_tier():
    _request_counts.clear()
    config = RateLimitConfig(
        anonymous_requests_per_window=1,
        authenticated_requests_per_window=2,
        premium_requests_per_window=3,
        window_seconds=60,
    )
    client = build_client(config=config)

    assert client.get("/ping").status_code == 200
    anonymous_limited = client.get("/ping")
    assert anonymous_limited.status_code == 429
    assert "Retry-After" in anonymous_limited.headers
    assert anonymous_limited.headers["X-RateLimit-Limit"] == "1"
    assert anonymous_limited.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in anonymous_limited.headers

    auth_headers = {"Authorization": "Bearer auth-tier-token"}
    assert client.get("/ping", headers=auth_headers).status_code == 200
    assert client.get("/ping", headers=auth_headers).status_code == 200
    auth_limited = client.get("/ping", headers=auth_headers)
    assert auth_limited.status_code == 429
    assert "Retry-After" in auth_limited.headers
    assert auth_limited.headers["X-RateLimit-Limit"] == "2"
    assert auth_limited.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in auth_limited.headers

    premium_headers = {"X-API-Key": "premium_test_key_for_429"}
    assert client.get("/ping", headers=premium_headers).status_code == 200
    assert client.get("/ping", headers=premium_headers).status_code == 200
    assert client.get("/ping", headers=premium_headers).status_code == 200
    premium_limited = client.get("/ping", headers=premium_headers)
    assert premium_limited.status_code == 429
    assert "Retry-After" in premium_limited.headers
    assert premium_limited.headers["X-RateLimit-Limit"] == "3"
    assert premium_limited.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in premium_limited.headers
