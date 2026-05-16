from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.middleware.ratelimit import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitTier,
    _request_counts,
    create_rate_limiter,
)


def build_client(config=None):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config or RateLimitConfig())

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/missing")
    async def missing():
        return {"ok": False}

    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limits(monkeypatch):
    _request_counts.clear()
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTHENTICATED_API_KEYS", raising=False)
    monkeypatch.delenv("PREMIUM_API_KEYS", raising=False)
    yield
    _request_counts.clear()


def jwt_token(secret, **claims):
    payload = {
        "sub": "user-1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        **claims,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def assert_rate_headers(response, limit, remaining=None):
    assert response.headers["X-RateLimit-Limit"] == str(limit)
    assert "X-RateLimit-Reset" in response.headers
    assert int(response.headers["X-RateLimit-Reset"]) > 0
    if remaining is not None:
        assert response.headers["X-RateLimit-Remaining"] == str(remaining)


def test_default_tier_limits_are_reported_from_auth_state(monkeypatch):
    secret = "test-secret-with-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET", secret)
    client = build_client()

    anonymous = client.get("/ok")
    authenticated_key = client.get("/ok", headers={"X-API-Key": "sk_test_123"})
    premium_key = client.get("/ok", headers={"X-API-Key": "pk_test_123"})
    authenticated_jwt = client.get(
        "/ok",
        headers={"Authorization": f"Bearer {jwt_token(secret)}"},
    )
    premium_jwt = client.get(
        "/ok",
        headers={"Authorization": f"Bearer {jwt_token(secret, premium=True)}"},
    )

    assert_rate_headers(anonymous, 60, 59)
    assert_rate_headers(authenticated_key, 300, 299)
    assert_rate_headers(premium_key, 1000, 999)
    assert_rate_headers(authenticated_jwt, 300, 299)
    assert_rate_headers(premium_jwt, 1000, 999)


@pytest.mark.parametrize(
    ("headers", "limit"),
    [
        ({}, 2),
        ({"X-API-Key": "sk_test_123"}, 3),
        ({"X-API-Key": "pk_test_123"}, 4),
    ],
)
def test_each_tier_is_enforced_independently(headers, limit):
    config = RateLimitConfig(
        anonymous_requests_per_window=2,
        authenticated_requests_per_window=3,
        premium_requests_per_window=4,
    )
    client = build_client(config)

    for expected_remaining in range(limit - 1, -1, -1):
        response = client.get("/ok", headers=headers)
        assert response.status_code == 200
        assert_rate_headers(response, limit, expected_remaining)

    limited = client.get("/ok", headers=headers)

    assert limited.status_code == 429
    assert limited.json()["error"] == "Rate limit exceeded"
    assert "Retry-After" in limited.headers
    assert int(limited.headers["Retry-After"]) > 0
    assert_rate_headers(limited, limit, 0)


def test_invalid_bearer_token_falls_back_to_anonymous(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = build_client()

    response = client.get("/ok", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 200
    assert_rate_headers(response, 60, 59)


def test_configured_premium_api_key_does_not_require_prefix():
    config = RateLimitConfig(premium_api_keys={"opaque-premium-key"})
    client = build_client(config)

    response = client.get("/ok", headers={"X-API-Key": "opaque-premium-key"})

    assert response.status_code == 200
    assert_rate_headers(response, 1000, 999)


def test_configured_api_key_sets_do_not_upgrade_unknown_keys():
    config = RateLimitConfig(authenticated_api_keys={"known-key"})
    client = build_client(config)

    known = client.get("/ok", headers={"X-API-Key": "known-key"})
    unknown = client.get("/ok", headers={"X-API-Key": "unknown-key"})

    assert_rate_headers(known, 300, 299)
    assert_rate_headers(unknown, 60, 59)


def test_request_state_can_supply_tier_and_identifier():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.middleware("http")
    async def add_auth_state(request, call_next):
        request.state.rate_limit_tier = RateLimitTier.PREMIUM
        request.state.rate_limit_identifier = "state-user"
        return await call_next(request)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    response = TestClient(app).get("/ok")

    assert response.status_code == 200
    assert_rate_headers(response, 1000, 999)


def test_rate_limit_headers_are_added_to_404_responses():
    client = build_client()

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert_rate_headers(response, 60, 59)


def test_legacy_config_and_factory_surface_still_work():
    config = RateLimitConfig(requests_per_window=2, burst_limit=7)
    limiter = create_rate_limiter(requests_per_minute=2, burst=7)

    assert config.requests_per_window == 2
    assert config.burst_limit == 7
    assert limiter.config.requests_per_window == 2
    assert limiter.config.burst_limit == 7
    assert limiter._is_rate_limited("127.0.0.1") == (False, 1)
    assert limiter._is_rate_limited("127.0.0.1") == (False, 0)

    limited, retry_after = limiter._is_rate_limited("127.0.0.1")
    assert limited is True
    assert retry_after > 0


def test_main_app_health_response_has_rate_limit_headers(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from api.main import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert_rate_headers(response, 60)
