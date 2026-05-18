import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.ratelimit import RateLimitMiddleware, _request_history
import time
import jwt
import os

# Set JWT secret for tests
os.environ["JWT_SECRET"] = "test_secret"

app = FastAPI()
app.add_middleware(RateLimitMiddleware)

@app.get("/")
async def root():
    return {"message": "ok"}

@app.get("/auth")
async def auth_route(request: Request):
    return {"message": "authenticated"}

@app.get("/health")
async def health():
    return {"status": "ok"}

client = TestClient(app)

def setup_function():
    _request_history.clear()

def test_anonymous_rate_limit():
    # Limit is 60. Burst is 10.
    # To avoid burst limit, we sleep every 10 requests.
    for i in range(6):
        for _ in range(10):
            response = client.get("/")
            assert response.status_code == 200
            assert response.headers["X-RateLimit-Tier"] == "anonymous"
        if i < 5:
            time.sleep(1.1) # Clear burst window
    
    # 61st request should be limited by total window
    response = client.get("/")
    assert response.status_code == 429
    assert response.json()["error"] == "Rate limit exceeded"
    assert "Retry-After" in response.headers

def test_authenticated_rate_limit():
    # Authenticated limit is 300
    token = jwt.encode({"sub": "user_123"}, "test_secret", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test first request
    response = client.get("/auth", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "300"
    assert response.headers["X-RateLimit-Tier"] == "authenticated"

def test_premium_rate_limit():
    # Premium limit is 1000
    headers = {"X-Premium-Key": "gold_key"}
    response = client.get("/", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert response.headers["X-RateLimit-Tier"] == "premium"

def test_burst_limit():
    # Anonymous burst limit is 10 per second
    for _ in range(10):
        response = client.get("/")
        assert response.status_code == 200
    
    # 11th request in same second should fail
    response = client.get("/")
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Tier"] == "anonymous"
    assert int(response.headers["Retry-After"]) <= 1

def test_headers_format():
    response = client.get("/")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
    
    # Reset should be a future epoch timestamp
    reset_val = int(response.headers["X-RateLimit-Reset"])
    assert reset_val > time.time()

def test_health_check_skipped():
    response = client.get("/health")
    assert response.status_code == 200
    # Headers should NOT be present if skipped
    assert "X-RateLimit-Limit" not in response.headers
