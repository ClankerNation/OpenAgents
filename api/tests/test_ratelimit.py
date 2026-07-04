import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig, _request_counts

client = TestClient(app)


def test_anonymous_tier_enforced():
    _request_counts.clear()
    response = client.get("/agents")
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "60"


def test_authenticated_tier_has_higher_limit():
    _request_counts.clear()
    response = client.get("/agents", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "300"


def test_premium_tier_has_highest_limit():
    _request_counts.clear()
    response = client.get("/agents", headers={"X-API-Key": "premium"})
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "1000"


def test_rate_limit_headers_present():
    _request_counts.clear()
    response = client.get("/agents")
    assert response.headers.get("X-RateLimit-Remaining") is not None
    assert response.headers.get("X-RateLimit-Reset") is not None


def test_429_includes_retry_after():
    _request_counts.clear()

    for _ in range(60):
        client.get("/agents")

    response = client.get("/agents")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    _request_counts.clear()


def test_premium_overrides_authenticated_limit():
    _request_counts.clear()
    response = client.get("/agents", headers={"Authorization": "Bearer token", "X-API-Key": "premium"})
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "1000"
