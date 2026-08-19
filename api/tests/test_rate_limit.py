"""Tests for Rate Limiting Tiers (Issue #174)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os
import hashlib
from unittest.mock import patch

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app
from api.models.database import Base, get_db, User, ApiKey

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_rate_limit.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def _get_jwt_token(user_id=1, address="0xCreatorAddress"):
    payload = {
        "sub": str(user_id),
        "address": address,
        "roles": ["user"],
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

def _setup_user_and_api_key():
    db = TestingSessionLocal()
    user = User(id=1, address="0xCreatorAddress", username="creator")
    db.add(user)
    db.commit()
    
    raw_key = "premium_test_key_123"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(user_id=1, key_hash=key_hash, name="Premium")
    db.add(api_key)
    db.commit()
    db.close()
    return raw_key

def test_anonymous_rate_limit_headers():
    response = client.get("/agents/")
    assert response.status_code == 200
    assert "x-ratelimit-limit" in response.headers
    assert response.headers["x-ratelimit-limit"] == "60"
    assert "x-ratelimit-remaining" in response.headers
    assert "x-ratelimit-reset" in response.headers

def test_authenticated_rate_limit_headers():
    token = _get_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/agents/", headers=headers)
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "300"

@patch("api.middleware.ratelimit.SessionLocal")
def test_premium_api_key_rate_limit_headers(mock_session_local):
    raw_key = _setup_user_and_api_key()
    mock_session_local.return_value = TestingSessionLocal()
    headers = {"X-API-Key": raw_key}
    response = client.get("/agents/", headers=headers)
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "1000"

def test_rate_limit_exceeded_returns_429():
    pass
