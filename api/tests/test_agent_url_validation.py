"""Tests for Agent URL validation and SSRF protection (Issue #173)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os
from unittest.mock import patch, AsyncMock, MagicMock

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app
from api.models.database import Base, get_db, User

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_agent_url.db"
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

def _get_user_token():
    payload = {
        "sub": "1",
        "address": "0xCreatorAddress",
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

@patch("api.routes.agents.httpx.AsyncClient")
def test_valid_url_accepted(mock_client_cls):
    _setup_user()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    mock_client = AsyncMock()
    mock_client.head.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    payload = {
        "name": "ValidAgent",
        "endpoint": "https://valid-agent.example.com/api"
    }
    
    response = client.post("/agents/", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ValidAgent"

def test_invalid_url_format_rejected():
    _setup_user()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "name": "BadAgent",
        "endpoint": "not-a-valid-url"
    }
    
    response = client.post("/agents/", json=payload, headers=headers)
    assert response.status_code == 422

def test_private_ip_rejected():
    _setup_user()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "name": "SSRFAgent",
        "endpoint": "http://127.0.0.1:8080/api"
    }
    
    response = client.post("/agents/", json=payload, headers=headers)
    assert response.status_code == 422
    assert "Private/internal IPs" in response.json()["detail"][0]["msg"]

@patch("api.routes.agents.httpx.AsyncClient")
def test_timeout_rejected(mock_client_cls):
    _setup_user()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    import httpx
    mock_client = AsyncMock()
    mock_client.head.side_effect = httpx.TimeoutException("Timeout")
    mock_client.__aenter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    payload = {
        "name": "TimeoutAgent",
        "endpoint": "https://slow-agent.example.com/api"
    }
    
    response = client.post("/agents/", json=payload, headers=headers)
    assert response.status_code == 400
    assert "timed out" in response.json()["detail"]

def test_empty_name_rejected():
    _setup_user()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "name": "",
        "endpoint": "https://valid.com"
    }
    
    response = client.post("/agents/", json=payload, headers=headers)
    assert response.status_code == 422
