import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.ratelimit import RateLimitMiddleware, _request_history
import time

app = FastAPI()
app.add_middleware(RateLimitMiddleware)

@app.get("/")
async def root():
    return {"message": "ok"}

@app.get("/auth")
async def auth_route(request: Request):
    request.state.user = {"id": "test_user"}
    return {"message": "authenticated"}

client = TestClient(app)

def setup_function():
    _request_history.clear()

def test_anonymous_rate_limit():
    # Limit is 60
    for _ in range(60):
        response = client.get("/")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "60"
    
    # 61st request should be limited
    response = client.get("/")
    assert response.status_code == 429
    assert response.json()["error"] == "Rate limit exceeded"
    assert "Retry-After" in response.headers

def test_premium_rate_limit():
    # Limit is 1000
    headers = {"X-Premium-Key": "gold_key"}
    for _ in range(5): # Just test headers and basic functionality to save time
        response = client.get("/", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "1000"

def test_headers_presence():
    response = client.get("/")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
