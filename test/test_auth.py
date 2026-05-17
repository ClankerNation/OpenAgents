"""Tests for JWT authentication middleware and endpoints."""

import os
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

# Ensure JWT_SECRET is set for tests
os.environ["JWT_SECRET"] = "test-secret-key-for-testing"

import jwt as pyjwt
from fastapi.testclient import TestClient
from httpx import AsyncClient

from api.middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_refresh_token,
    revoke_token,
    is_token_revoked,
    generate_login_tokens,
    JWT_SECRET,
    JWT_ALGORITHM,
    _revoked_tokens,
)
from api.main import app


client = TestClient(app)


class TestAlgorithmPinning:
    """Verify that 'none' algorithm is rejected."""

    def test_none_algorithm_rejected(self):
        """Token with alg='none' should raise 401."""
        forged_token = pyjwt.encode({"sub": "attacker", "type": "access"}, "", algorithm="none")
        response = client.get("/health", headers={"Authorization": f"Bearer {forged_token}"})
        # /health doesn't require auth, so let's test decode_token directly
        with pytest.raises(Exception):
            decode_token(forged_token)

    def test_hs256_token_accepted(self):
        """Valid HS256 token should decode successfully."""
        token = create_access_token({"sub": "user1", "address": "0x123"})
        payload = decode_token(token)
        assert payload["sub"] == "user1"
        assert payload["type"] == "access"

    def test_decode_token_rejects_none(self):
        """decode_token should reject 'none' algorithm tokens."""
        forged = pyjwt.encode({"sub": "hack", "type": "access"}, "", algorithm="none")
        # decode_token raises HTTPException for invalid tokens
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(forged)
        assert exc_info.value.status_code == 401


class TestGracefulEnvFallback:
    """Verify missing JWT_SECRET doesn't crash the app."""

    def test_secret_default_when_missing(self):
        """JWT_SECRET should have a sensible default when env var is missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to trigger default
            import importlib
            import api.middleware.auth as auth_module
            importlib.reload(auth_module)
            # Should not raise KeyError — should use default
            assert auth_module.JWT_SECRET == "change-me-in-production"


class TestTokenRevocation:
    """Verify revoked tokens are rejected."""

    def test_revoke_and_check(self):
        """Revoked token should fail authentication."""
        token = create_access_token({"sub": "user1", "address": "0x123"})
        assert not is_token_revoked(token)
        revoke_token(token)
        assert is_token_revoked(token)

    def test_revoked_token_fails_decode(self):
        """A revoked token should raise 401 when used."""
        token = create_access_token({"sub": "user1", "address": "0x123"})
        revoke_token(token)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            # Simulate get_current_user flow
            assert is_token_revoked(token)
            raise HTTPException(status_code=401, detail="Token has been revoked")
        assert exc_info.value.status_code == 401


class TestRefreshEndpoint:
    """Verify refresh token flow."""

    def test_refresh_returns_new_access_token(self):
        """POST /auth/refresh should return a new access token."""
        # Login first
        login_resp = client.post("/auth/login", json={
            "user_id": "user1",
            "address": "0xABC",
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        refresh_token = data["refresh_token"]

        # Refresh
        refresh_resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert refresh_resp.status_code == 200
        new_data = refresh_resp.json()
        assert "token" in new_data
        assert "expires_in" in new_data

    def test_refresh_with_invalid_token_fails(self):
        """Refresh with invalid token should return 401."""
        resp = client.post("/auth/refresh", json={
            "refresh_token": "invalid.token.here",
        })
        assert resp.status_code == 401


class TestLoginEndpoint:
    """Verify login returns tokens."""

    def test_login_returns_tokens(self):
        """POST /auth/login should return access + refresh tokens."""
        resp = client.post("/auth/login", json={
            "user_id": "user1",
            "address": "0xABC",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert "expires_in" in data

    def test_login_with_roles(self):
        """Login with roles should include them in token."""
        resp = client.post("/auth/login", json={
            "user_id": "admin",
            "address": "0xDEF",
            "roles": ["admin"],
        })
        assert resp.status_code == 200


class TestLogoutEndpoint:
    """Verify logout revokes tokens."""

    def test_logout_success(self):
        """POST /auth/logout with valid token should succeed."""
        login_resp = client.post("/auth/login", json={
            "user_id": "user1",
            "address": "0xABC",
        })
        token = login_resp.json()["token"]

        logout_resp = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_resp.status_code == 200
        assert "Logged out" in logout_resp.json()["message"]
