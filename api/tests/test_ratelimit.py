import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.ratelimit import RateLimitMiddleware, _request_history, JWT_SECRET, JWT_ALGORITHM
import time
import jwt

app = FastAPI()
app.add_middleware(RateLimitMiddleware)

@app.get("/")
async def root():
    return {"message": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok"}

client = TestClient(app)

def setup_function():
    _request_history.clear()

def create_token(user_id: str):
    return jwt.encode({"sub": user_id}, JWT_SECRET, algorithm=JWT_ALGORITHM)

def test_anonymous_rate_limit():
    # Limit is 60, but burst is 10
    # To test the 60-second limit without tripping burst, we'd need to sleep.
    # Instead, we test that it trips the BURST limit first.
    for _ in range(10):
        response = client.get("/")
        assert response.status_code == 200
    
    # 11th request should trip burst limit (10)
    response = client.get("/")
    assert response.status_code == 429
    assert response.json()["error"] == "Rate limit exceeded"
    assert response.headers["X-RateLimit-Tier"] == "anonymous"

def test_authenticated_rate_limit_proactive():
    token = create_token("test_user")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Auth limit is 300, burst is 50
    for _ in range(50):
        response = client.get("/", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Tier"] == "authenticated"
    
    # 51st request should be limited by burst
    response = client.get("/", headers=headers)
    assert response.status_code == 429

def test_premium_rate_limit():
    headers = {"X-Premium-Key": "gold_key"}
    # Premium burst is 100
    for _ in range(100):
        response = client.get("/", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Tier"] == "premium"
    
    response = client.get("/", headers=headers)
    assert response.status_code == 429

def test_health_bypass():
    # Should not be rate limited
    for _ in range(120):
        response = client.get("/health")
        assert response.status_code == 200

def test_reset_header_is_epoch():
    response = client.get("/")
    reset_ts = int(response.headers["X-RateLimit-Reset"])
    assert reset_ts > time.time()
    assert reset_ts < time.time() + 70
