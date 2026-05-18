import os
# Set JWT_SECRET in environment before any import to prevent KeyError in auth.py
os.environ["JWT_SECRET"] = "test_jwt_secret"

import time
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig, _request_counts
from api.middleware.auth import create_access_token

# Create a clean Test FastAPI App for rate limiting tests
app = FastAPI()

# Configure RateLimitMiddleware with small window to make testing fast, or we can use custom config
# Since tests need to verify 60, 300, 1000 limits, making 60 requests in unit tests would be slow or we can reset/manipulate _request_counts cache directly!
config = RateLimitConfig(
    window_seconds=60,
    anon_limit=2,
    auth_limit=3,
    premium_limit=5
)
app.add_middleware(RateLimitMiddleware, config=config)

@app.get("/test")
async def sample_endpoint():
    return PlainTextResponse("success")

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_cache():
    # Clear the in-memory rate limit counts before each test
    _request_counts.clear()

def test_anonymous_rate_limiting():
    # 1. Test Anonymous Tier (Limit: 2)
    # First request
    response = client.get("/test")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "1"
    assert "X-RateLimit-Reset" in response.headers
    
    # Second request
    response = client.get("/test")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "0"
    
    # Third request -> 429 Rate limited
    response = client.get("/test")
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers
    assert response.json() == {
        "error": "Rate limit exceeded",
        "retry_after": int(response.headers["Retry-After"])
    }

def test_authenticated_rate_limiting():
    # 2. Test Authenticated Tier (Limit: 3)
    # Create an access token for standard user
    token = create_access_token({"sub": "user123", "roles": ["user"]})
    headers = {"Authorization": f"Bearer {token}"}
    
    # First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "3"
    assert response.headers["X-RateLimit-Remaining"] == "2"
    
    # Second request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "1"

    # Third request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "0"
    
    # Fourth request -> 429 Rate limited
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers
    assert response.json()["error"] == "Rate limit exceeded"

def test_premium_rate_limiting():
    # 3. Test Premium Tier (Limit: 5)
    # Create an access token for premium user
    token = create_access_token({"sub": "premium_user", "roles": ["premium"]})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Send 5 requests
    for i in range(5):
        response = client.get("/test", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == str(5 - i - 1)
        
    # Sixth request -> 429 Rate limited
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers
    assert response.json()["error"] == "Rate limit exceeded"
