import os
import sys
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig, _request_counts

# Custom small limits for testing threshold crossings quickly
test_config = RateLimitConfig(
    anonymous_limit=3,
    authenticated_limit=5,
    premium_limit=8,
    window_seconds=60,
)

app = FastAPI()
app.add_middleware(RateLimitMiddleware, config=test_config)


@app.get("/sample")
async def sample_endpoint():
    return {"message": "ok"}


@app.get("/health")
async def health_endpoint():
    return {"status": "healthy"}


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    _request_counts.clear()
    yield
    _request_counts.clear()


def test_anonymous_tier_and_headers():
    """Verify anonymous callers receive limit of 60 (or test configured 3) and proper headers."""
    resp = client.get("/sample", headers={"X-Forwarded-For": "192.168.1.100"})
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "3"
    assert resp.headers["X-RateLimit-Remaining"] == "2"
    assert "X-RateLimit-Reset" in resp.headers


def test_authenticated_tier():
    """Verify authenticated callers with API key receive authenticated limit (5)."""
    resp = client.get("/sample", headers={"X-API-Key": "my_standard_key"})
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "5"
    assert resp.headers["X-RateLimit-Remaining"] == "4"


def test_authenticated_bearer_token():
    """Verify authenticated callers with Bearer token receive authenticated limit (5)."""
    resp = client.get("/sample", headers={"Authorization": "Bearer standard_user_jwt_token"})
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "5"
    assert resp.headers["X-RateLimit-Remaining"] == "4"


def test_premium_tier_api_key():
    """Verify premium callers receive premium limit (8)."""
    resp = client.get("/sample", headers={"X-API-Key": "sk_premium_key_12345"})
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "8"
    assert resp.headers["X-RateLimit-Remaining"] == "7"


def test_premium_tier_bearer_token():
    """Verify premium callers with premium bearer token receive premium limit (8)."""
    resp = client.get("/sample", headers={"Authorization": "Bearer token_for_premium_agent"})
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "8"
    assert resp.headers["X-RateLimit-Remaining"] == "7"


def test_429_rate_limit_exceeded_with_retry_after():
    """Verify that exceeding limit triggers 429 with Retry-After and rate limit headers."""
    ip = "192.168.1.200"
    for i in range(3):
        r = client.get("/sample", headers={"X-Forwarded-For": ip})
        assert r.status_code == 200

    # 4th request exceeds anonymous limit of 3
    r4 = client.get("/sample", headers={"X-Forwarded-For": ip})
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers
    assert int(r4.headers["Retry-After"]) > 0
    assert r4.headers["X-RateLimit-Limit"] == "3"
    assert r4.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in r4.headers
    body = r4.json()
    assert body["error"] == "Rate limit exceeded"
    assert body["tier"] == "anonymous"


def test_health_check_exempt():
    """Verify health endpoint is exempt from rate limiting."""
    for _ in range(10):
        r = client.get("/health")
        assert r.status_code == 200


if __name__ == "__main__":
    pytest.main(["-v", __file__])
