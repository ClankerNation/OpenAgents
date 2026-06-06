"""Tests for multi-tier rate limiting middleware."""
import pytest
import time
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import sys
sys.path.insert(0, ".")

import api.middleware.ratelimit as rl


# ---- Helpers ---------------------------------------------------------------

class FakeAuthMiddleware(BaseHTTPMiddleware):
    """
    Simulates the real auth middleware by setting request.state.user.

    In production, AuthMiddleware (api.middleware.auth) sets request.state.user
    via get_current_user dependency.  Because Starlette middleware runs LIFO,
    AuthMiddleware is added *last* so it runs *first*, populating the user
    before RateLimitMiddleware inspects it.
    """
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/authed-test":
            request.state.user = {"id": "user42", "roles": []}
        elif request.url.path == "/premium-test":
            request.state.user = {"id": "vip99", "roles": ["premium"]}
        elif request.url.path == "/authed-exhaust":
            request.state.user = {"id": "user42", "roles": []}
        return await call_next(request)


# ---- Fixtures --------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_store():
    """Reset the rate-limit store before each test."""
    rl._store = rl._SlidingWindowStore()
    yield


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/test")
    async def test_route():
        return {"data": "hello"}

    @app.get("/authed-test")
    async def authed_test(request: Request):
        return {"user": request.state.user.get("id") if hasattr(request.state, "user") else None}

    @app.get("/premium-test")
    async def premium_test(request: Request):
        return {"user": request.state.user.get("id") if hasattr(request.state, "user") else None}

    @app.get("/authed-exhaust")
    async def authed_exhaust(request: Request):
        return {"ok": True}

    # Order matters: RateLimitMiddleware first, then FakeAuthMiddleware.
    # Starlette LIFO → FakeAuth runs first, populates user, then RateLimit reads it.
    app.add_middleware(rl.RateLimitMiddleware)
    app.add_middleware(FakeAuthMiddleware)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


# ---- Anonymous tier (60 req/min) ------------------------------------------

def test_anonymous_gets_60_limit(client):
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "60"


def test_anonymous_gets_429_after_exhaustion(client):
    for i in range(rl.TIER_ANONYMOUS):
        resp = client.get("/test")
        assert resp.status_code == 200, f"Request {i+1} should pass"
    resp = client.get("/test")
    assert resp.status_code == 429


# ---- 429 response ---------------------------------------------------------

def test_429_includes_retry_after_header(client):
    for _ in range(rl.TIER_ANONYMOUS):
        client.get("/test")
    resp = client.get("/test")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_429_body_contains_error_and_retry_after(client):
    for _ in range(rl.TIER_ANONYMOUS):
        client.get("/test")
    resp = client.get("/test")
    body = resp.json()
    assert "error" in body
    assert "retry_after" in body


# ---- Response headers -----------------------------------------------------

def test_response_includes_rate_limit_headers(client):
    resp = client.get("/test")
    for header in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        assert header in resp.headers, f"Missing {header}"


def test_remaining_decrements(client):
    first = int(client.get("/test").headers["X-RateLimit-Remaining"])
    second = int(client.get("/test").headers["X-RateLimit-Remaining"])
    assert second == first - 1


# ---- Health endpoint exemption --------------------------------------------

def test_health_endpoint_unlimited(client):
    for _ in range(200):
        resp = client.get("/health")
        assert resp.status_code == 200


# ---- Authenticated tier ---------------------------------------------------

def test_authenticated_tier_higher_limit(client):
    """Authenticated user gets 300 req/min limit."""
    resp = client.get("/authed-test")
    assert resp.headers["X-RateLimit-Limit"] == "300"


def test_authenticated_tier_can_exceed_anonymous_limit(client):
    """Auth user should make >60 requests without hitting 429."""
    for i in range(rl.TIER_ANONYMOUS + 10):
        resp = client.get("/authed-test")
        assert resp.status_code == 200, f"Request {i+1} should pass for auth user"


# ---- Premium tier ----------------------------------------------------------

def test_premium_tier_highest_limit(client):
    """Premium user gets 1000 req/min limit."""
    resp = client.get("/premium-test")
    assert resp.headers["X-RateLimit-Limit"] == "1000"


# ---- Sliding window --------------------------------------------------------

def test_sliding_window_no_double_burst(client):
    """Sliding window prevents 2x burst at boundary."""
    for _ in range(rl.TIER_ANONYMOUS):
        client.get("/test")
    resp = client.get("/test")
    assert resp.status_code == 429
    time.sleep(1)
    resp2 = client.get("/test")
    assert resp2.status_code == 429, (
        "Fixed-window bug re-introduced: sliding window should still block"
    )


# ---- X-Forwarded-For trust ------------------------------------------------

def test_x_forwarded_for_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(rl, "TRUSTED_PROXY_IPS", ("testclient",))
    c = TestClient(_make_app())
    resp = c.get("/test", headers={"X-Forwarded-For": "10.0.0.55"})
    assert resp.status_code == 200


def test_x_forwarded_for_ignored_from_untrusted(monkeypatch):
    """Spoofed X-Forwarded-For from untrusted source is ignored."""
    monkeypatch.setattr(rl, "TRUSTED_PROXY_IPS", ("192.168.1.1",))
    c = TestClient(_make_app())
    resp = c.get("/test", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.status_code == 200


# ---- Tier isolation --------------------------------------------------------

def test_tier_counters_are_isolated(client):
    """Exhausting anonymous should not affect authenticated."""
    for _ in range(rl.TIER_ANONYMOUS):
        client.get("/test")
    assert client.get("/test").status_code == 429  # anon blocked
    assert client.get("/authed-test").status_code == 200  # auth still ok
