"""Tests for authentication middleware."""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from api.middleware.auth import (
    get_current_user,
    generate_api_key,
    revoke_api_key,
    list_api_keys,
    create_access_token,
    generate_login_tokens,
)


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return {"user": user}

    @app.get("/admin")
    async def admin(user=Depends(get_current_user)):
        return {"user": user}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_jwt_authentication(client):
    """JWT bearer token authentication works."""
    tokens = generate_login_tokens("user1", "0xabc", ["user"])
    response = client.get("/protected", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user1"
    assert response.json()["user"]["auth_method"] == "jwt"


def test_api_key_authentication(client):
    """API key authentication works."""
    key_data = generate_api_key("user2", "0xdef", ["user"])
    response = client.get("/protected", headers={"X-API-Key": key_data["api_key"]})
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user2"
    assert response.json()["user"]["auth_method"] == "api_key"


def test_no_auth_returns_401(client):
    """No authentication returns 401."""
    response = client.get("/protected")
    assert response.status_code == 401


def test_invalid_jwt_returns_401(client):
    """Invalid JWT returns 401."""
    response = client.get("/protected", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_invalid_api_key_returns_401(client):
    """Invalid API key returns 401."""
    response = client.get("/protected", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


def test_revoked_api_key_returns_401(client):
    """Revoked API key returns 401."""
    key_data = generate_api_key("user3", "0xghi", ["user"])
    revoke_api_key(key_data["id"])
    response = client.get("/protected", headers={"X-API-Key": key_data["api_key"]})
    assert response.status_code == 401


def test_generate_api_key():
    """API key generation returns key and id."""
    key_data = generate_api_key("user4", "0xjkl", ["admin"], premium=True)
    assert "api_key" in key_data
    assert "id" in key_data
    assert key_data["premium"] is True


def test_list_api_keys():
    """List API keys for a user."""
    generate_api_key("user5", "0xmno", ["user"])
    keys = list_api_keys("user5")
    assert len(keys) >= 1
    assert "id" in keys[0]


def test_premium_api_key():
    """Premium API key is identified correctly."""
    key_data = generate_api_key("user6", "0xpqr", ["user"], premium=True)
    assert key_data["premium"] is True
