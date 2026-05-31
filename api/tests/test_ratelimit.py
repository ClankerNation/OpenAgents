from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


def _build_client(config: RateLimitConfig | None = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config or RateLimitConfig())

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return TestClient(app)


def setup_function():
    _request_counts.clear()


def teardown_function():
    _request_counts.clear()


def test_anonymous_tier_limit_header():
    client = _build_client()
    response = client.get("/test")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "60"


def test_authenticated_tier_limit_header():
    client = _build_client()
    response = client.get("/test", headers={"Authorization": "Bearer token-123"})
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "300"


def test_premium_tier_limit_header():
    client = _build_client()
    response = client.get("/test", headers={"X-API-Key": "pk_live_123"})
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "1000"


def test_rate_limit_headers_present_on_success():
    client = _build_client()
    response = client.get("/test")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_429_includes_retry_after_and_rate_headers():
    client = _build_client(
        RateLimitConfig(
            requests_per_window=2,
            anonymous_requests_per_window=2,
            authenticated_requests_per_window=2,
            premium_requests_per_window=2,
        )
    )
    assert client.get("/test").status_code == 200
    assert client.get("/test").status_code == 200

    response = client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in response.headers

