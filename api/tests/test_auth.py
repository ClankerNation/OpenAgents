"""Tests for JWT and API key authentication.

IMPORTANT: Run these tests in ISOLATION (pytest tests/test_auth.py only)
to ensure clean env vars.
"""

import os
import jwt
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import Depends

JWT_SECRET = os.environ.get("JWT_SECRET", "test-secret-key")

from middleware.auth import get_current_user

app = FastAPI()


@app.get("/protected")
async def protected(user=Depends(get_current_user)):
    return {"user_id": user["id"], "auth_method": user.get("auth_method")}


client = TestClient(app)


class TestJWTAuth:
    def test_valid_jwt(self):
        token = jwt.encode(
            {"sub": "user-1", "address": "0x123", "roles": [], "type": "access"},
            JWT_SECRET,
            algorithm="HS256",
        )
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-1"
        assert data["auth_method"] == "jwt"

    def test_no_auth_returns_401(self):
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = client.get("/protected", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        token = jwt.encode(
            {
                "sub": "user-1",
                "type": "access",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


class TestAPIKeyAuth:
    def test_valid_api_key(self):
        resp = client.get("/protected", headers={"X-API-Key": "sk-test-key-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-abc"
        assert data["auth_method"] == "api_key"

    def test_premium_api_key(self):
        resp = client.get("/protected", headers={"X-API-Key": "sk-premium-456"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-premium"

    def test_invalid_api_key_returns_401(self):
        resp = client.get("/protected", headers={"X-API-Key": "sk-invalid-key"})
        assert resp.status_code == 401

    def test_empty_api_key_header_ignored(self):
        resp = client.get("/protected", headers={"X-API-Key": ""})
        assert resp.status_code == 401

    def test_api_key_takes_precedence_over_jwt(self):
        token = jwt.encode(
            {"sub": "jwt-user", "type": "access"},
            JWT_SECRET,
            algorithm="HS256",
        )
        resp = client.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {token}",
                "X-API-Key": "sk-test-key-123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-abc"
        assert data["auth_method"] == "api_key"
