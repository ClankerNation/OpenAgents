"""Tests for API Key authentication (Issue #177)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os
import hashlib

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app
from api.models.database import Base, get_db, User, ApiKey
from api.middleware.auth import generate_api_key, hash_api_key

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_api_key.db"
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

def _setup_user():
    db = TestingSessionLocal()
    user = User(id=1, address="0xCreatorAddress", username="creator")
    db.add(user)
    db.commit()
    db.close()

def test_create_api_key_with_jwt():
    _setup_user()
    token = _get_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/auth/api-keys", json={"name": "Test Key"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "key" in data
    assert data["name"] == "Test Key"
    
    # Verify hash is stored
    db = TestingSessionLocal()
    db_key = db.query(ApiKey).filter(ApiKey.user_id == 1).first()
    assert db_key is not None
    assert db_key.key_hash == hashlib.sha256(data["key"].encode()).hexdigest()
    db.close()

def test_auth_with_api_key():
    _setup_user()
    token = _get_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create key
    response = client.post("/auth/api-keys", json={}, headers=headers)
    raw_key = response.json()["key"]
    
    # Use API key to access a protected endpoint (e.g., list api keys)
    api_headers = {"X-API-Key": raw_key}
    response = client.get("/auth/api-keys", headers=api_headers)
    assert response.status_code == 200

def test_revoke_api_key():
    _setup_user()
    token = _get_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create key
    response = client.post("/auth/api-keys", json={}, headers=headers)
    key_id = response.json()["id"]
    raw_key = response.json()["key"]
    
    # Revoke it
    response = client.delete(f"/auth/api-keys/{key_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    
    # Try to use revoked key
    api_headers = {"X-API-Key": raw_key}
    response = client.get("/auth/api-keys", headers=api_headers)
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()

def test_invalid_api_key_rejected():
    _setup_user()
    api_headers = {"X-API-Key": "invalid_random_key_string"}
    response = client.get("/auth/api-keys", headers=api_headers)
    assert response.status_code == 401
