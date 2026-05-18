import pytest
import time
import os
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set JWT_SECRET environment variable for testing
os.environ["JWT_SECRET"] = "test_jwt_secret"

from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig, _request_counts

# Create a clean FastAPI app for testing
app = FastAPI()
app.add_middleware(RateLimitMiddleware, config=RateLimitConfig(window_seconds=60))


@app.get("/test")
async def sample_endpoint():
    return {"message": "success"}


@app.get("/health")
async def health_endpoint():
    return {"status": "ok"}


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear request counts before each test."""
    _request_counts.clear()


def test_health_endpoint_bypasses_ratelimit():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers


def test_anonymous_tier_limit():
    client = TestClient(app)
    client_ip = "127.0.0.1"
    key = f"ip:{client_ip}"
    headers = {"X-Forwarded-For": client_ip}
    
    # 1. First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "59"
    assert "X-RateLimit-Reset" in response.headers

    # 2. Simulate limit reached
    _request_counts[key] = (60, time.time())
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["Retry-After"] is not None
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" in response.headers


def test_authenticated_tier_jwt():
    client = TestClient(app)
    
    # Generate a standard JWT token (no premium role)
    token = jwt.encode({"sub": "user123", "roles": ["user"]}, "test_jwt_secret", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "300"
    assert response.headers["X-RateLimit-Remaining"] == "299"
    
    # 2. Simulate limit reached
    key = f"auth:Bearer {token}"
    _request_counts[key] = (300, time.time())
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "300"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers


def test_authenticated_tier_api_key():
    client = TestClient(app)
    headers = {"X-API-Key": "standard-api-key"}
    
    # 1. First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "300"
    assert response.headers["X-RateLimit-Remaining"] == "299"

    # 2. Simulate limit reached
    key = "apikey:standard-api-key"
    _request_counts[key] = (300, time.time())
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "300"
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_premium_tier_jwt():
    client = TestClient(app)
    
    # Generate a premium JWT token
    token = jwt.encode({"sub": "user_premium", "roles": ["premium"]}, "test_jwt_secret", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert response.headers["X-RateLimit-Remaining"] == "999"

    # 2. Simulate limit reached
    key = f"auth:Bearer {token}"
    _request_counts[key] = (1000, time.time())
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_premium_tier_api_key():
    client = TestClient(app)
    headers = {"X-API-Key": "my-premium-secret-key"}
    
    # 1. First request
    response = client.get("/test", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert response.headers["X-RateLimit-Remaining"] == "999"

    # 2. Simulate limit reached
    key = "apikey:my-premium-secret-key"
    _request_counts[key] = (1000, time.time())
    response = client.get("/test", headers=headers)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "1000"
    assert response.headers["X-RateLimit-Remaining"] == "0"
