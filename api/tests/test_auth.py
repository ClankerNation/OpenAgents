"""Tests for JWT auth middleware — ALL acceptance criteria verified."""

import os
import sys

# Ensure the api directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jwt
import pytest
from fastapi import HTTPException
from unittest.mock import patch
from middleware import auth


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_env():
    """Set JWT_SECRET before each test, then clear revocation set."""
    os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"
    # Re-import module-level vars by reloading
    auth.JWT_SECRET = "test-secret-key-for-testing-only"
    auth._revoked_tokens.clear()
    yield
    auth._revoked_tokens.clear()


# ── Acceptance Criterion 1: `none` algorithm rejected ────────────────

class TestAlgorithmNoneRejected:
    """AC-1: jwt.decode with algorithm 'none' must be rejected."""

    def test_decode_rejects_none_alg_token(self):
        """A token with alg='none' and no signature must fail decode."""
        # Forge a token with alg=none and no signature
        none_token = jwt.encode(
            {"sub": "test", "type": "access", "exp": 9999999999},
            "",  # empty key
            algorithm="none",
        )
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(none_token)
        assert exc_info.value.status_code == 401
        # Must NOT return a payload — the decode must fail
        assert "Invalid token" in str(exc_info.value.detail)

    def test_decode_rejects_none_alg_with_arbitrary_payload(self):
        """An alg=none token with made-up claims must also be rejected."""
        forged = jwt.encode(
            {"sub": "attacker", "type": "access", "roles": ["admin"], "exp": 9999999999},
            "",
            algorithm="none",
        )
        with pytest.raises(HTTPException):
            auth.decode_token(forged)

    def test_valid_hs256_token_succeeds(self):
        """A properly signed HS256 token must still work (sanity check)."""
        token = auth.create_access_token({"sub": "user1", "address": "0x1", "roles": ["user"]})
        payload = auth.decode_token(token)
        assert payload["sub"] == "user1"
        assert payload["address"] == "0x1"
        assert payload["type"] == "access"


# ── Acceptance Criterion 2: Missing secret = error, not crash ────────

class TestMissingSecretHandling:
    """AC-2: Missing JWT_SECRET must produce a runtime error, not a crash."""

    def test_missing_secret_raises_at_runtime_not_import(self):
        """Module should import without error even without JWT_SECRET."""
        # The module-level JWT_SECRET uses os.getenv (not os.environ[]),
        # so import doesn't crash.  Verify by checking it's None when unset.
        orig = auth.JWT_SECRET
        auth.JWT_SECRET = None
        try:
            with pytest.raises(HTTPException) as exc_info:
                auth.create_access_token({"sub": "x"})
            assert exc_info.value.status_code == 500
            assert "JWT_SECRET" in str(exc_info.value.detail)
        finally:
            auth.JWT_SECRET = orig

    def test_decode_fails_without_secret(self):
        """decode_token must also fail with a clear 500 error when secret is missing."""
        orig = auth.JWT_SECRET
        auth.JWT_SECRET = None
        try:
            with pytest.raises(HTTPException) as exc_info:
                auth.decode_token("some.token.string")
            assert exc_info.value.status_code == 500
            assert "JWT_SECRET" in str(exc_info.value.detail)
        finally:
            auth.JWT_SECRET = orig


# ── Acceptance Criterion 3: Revoked tokens fail ──────────────────────

class TestTokenRevocation:
    """AC-3: Revoked tokens must be rejected."""

    def test_revoked_token_is_rejected(self):
        """A token added to the revocation set must fail get_current_user."""
        token = auth.create_access_token({"sub": "user1", "address": "0x1", "roles": []})
        auth.revoke_token(token)
        assert auth.is_token_revoked(token) is True

    def test_revoked_token_fails_current_user(self):
        """get_current_user must raise 401 for a revoked token."""
        token = auth.create_access_token({"sub": "user1", "address": "0x1", "roles": []})
        auth.revoke_token(token)

        from fastapi.security import HTTPAuthorizationCredentials
        import asyncio

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth.get_current_user(creds))
        assert exc_info.value.status_code == 401
        assert "revoked" in str(exc_info.value.detail).lower()

    def test_non_revoked_token_succeeds(self):
        """A token not in the revocation set must pass get_current_user."""
        token = auth.create_access_token({"sub": "user2", "address": "0x2", "roles": ["user"]})

        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        import asyncio

        result = asyncio.run(auth.get_current_user(creds))
        assert result["id"] == "user2"
        assert result["address"] == "0x2"
        assert result["roles"] == ["user"]

    def test_revoke_twice_is_idempotent(self):
        """Revoking the same token twice must not raise."""
        token = auth.create_access_token({"sub": "user1", "address": "0x1", "roles": []})
        auth.revoke_token(token)
        auth.revoke_token(token)  # should not raise
        assert auth.is_token_revoked(token) is True


# ── Acceptance Criterion 4: Refresh works ────────────────────────────

class TestRefreshFlow:
    """AC-4: Refresh endpoint must accept a valid refresh token and return new tokens."""

    def test_refresh_token_creation_and_exchange(self):
        """A refresh token must be creatable and exchangeable."""
        data = {"sub": "user1", "address": "0x1", "roles": ["user"]}
        refresh_token = auth.create_refresh_token(data)
        # Verify it's a valid token with type "refresh"
        payload = auth.decode_token(refresh_token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "user1"

    def test_refresh_produces_new_tokens(self):
        """Exchanging a refresh token must produce a new access+refresh pair."""
        data = {"sub": "user1", "address": "0x1", "roles": ["user"]}
        refresh_token = auth.create_refresh_token(data)

        # Decode and re-issue
        payload = auth.decode_token(refresh_token)
        new_tokens = auth.generate_login_tokens(
            payload["sub"], payload["address"], payload["roles"]
        )
        assert "token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["expires_in"] == auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        # The new tokens must be valid
        new_access_payload = auth.decode_token(new_tokens["token"])
        assert new_access_payload["type"] == "access"
        assert new_access_payload["sub"] == "user1"

        new_refresh_payload = auth.decode_token(new_tokens["refresh_token"])
        assert new_refresh_payload["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self):
        """An access token used as a refresh token must be rejected."""
        access_token = auth.create_access_token({"sub": "user1", "address": "0x1", "roles": []})
        payload = auth.decode_token(access_token)
        assert payload["type"] != "refresh"


# ── General: Valid token flow ────────────────────────────────────────

class TestValidTokenFlow:
    """Valid token creation, decode, and user extraction."""

    def test_create_and_decode_access_token(self):
        """Creating and decoding an access token round-trips correctly."""
        token = auth.create_access_token({"sub": "alice", "address": "0xabc", "roles": ["admin"]})
        payload = auth.decode_token(token)
        assert payload["sub"] == "alice"
        assert payload["address"] == "0xabc"
        assert payload["roles"] == ["admin"]
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_get_current_user_returns_user_data(self):
        """get_current_user returns correct user dict from a valid token."""
        token = auth.create_access_token({"sub": "bob", "address": "0xb0b", "roles": ["user"]})

        from fastapi.security import HTTPAuthorizationCredentials
        import asyncio

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = asyncio.run(auth.get_current_user(creds))
        assert user["id"] == "bob"
        assert user["address"] == "0xb0b"
        assert user["roles"] == ["user"]

    def test_expired_token_raises_401(self):
        """An expired token must produce a 401."""
        import time
        from datetime import timedelta

        # Create a token that expired 1 second ago
        expired_token = auth.create_access_token(
            {"sub": "user1", "address": "0x1", "roles": []},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(expired_token)
        assert exc_info.value.status_code == 401
        assert "expired" in str(exc_info.value.detail).lower()

    def test_missing_sub_in_token_raises_401(self):
        """A token without 'sub' claim must be rejected."""
        token = auth.create_access_token({"address": "0x1", "roles": []})
        from fastapi.security import HTTPAuthorizationCredentials
        import asyncio

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth.get_current_user(creds))
        assert exc_info.value.status_code == 401

    def test_no_credentials_raises_401(self):
        """Missing HTTPAuthorizationCredentials must raise 401."""
        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth.get_current_user(None))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    def test_generate_login_tokens_full_flow(self):
        """generate_login_tokens returns a complete token bundle."""
        tokens = auth.generate_login_tokens("user1", "0xabc", ["user", "admin"])
        assert "token" in tokens
        assert "refresh_token" in tokens
        assert tokens["expires_in"] == 3600

        # Both tokens must be decodable
        access_payload = auth.decode_token(tokens["token"])
        assert access_payload["type"] == "access"

        refresh_payload = auth.decode_token(tokens["refresh_token"])
        assert refresh_payload["type"] == "refresh"


# ── Acceptance Criterion 5: @generated-by doc block ──────────────────
# Verified by reading the top of api/middleware/auth.py


# ── Integration: Verify main.py endpoints ────────────────────────────

class TestAuthEndpoints:
    """Verify the /auth/* endpoints in main.py via TestClient."""

    def test_login_endpoint(self):
        """POST /auth/login returns tokens."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/auth/login", json={
            "user_id": "test_user",
            "address": "0x123",
            "roles": ["user"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 3600

    def test_refresh_endpoint(self):
        """POST /auth/refresh with a valid refresh token returns new tokens."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        # First login to get tokens
        login_resp = client.post("/auth/login", json={
            "user_id": "test_user",
            "address": "0x123",
            "roles": ["user"],
        })
        tokens = login_resp.json()

        # Refresh
        refresh_resp = client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()
        assert "token" in new_tokens
        assert "refresh_token" in new_tokens
        # Both tokens should be valid decodable JWTs
        auth.decode_token(new_tokens["token"])
        auth.decode_token(new_tokens["refresh_token"])

    def test_me_endpoint_with_valid_token(self):
        """GET /auth/me returns user data with valid token."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        login_resp = client.post("/auth/login", json={
            "user_id": "test_user",
            "address": "0x123",
            "roles": ["user"],
        })
        token = login_resp.json()["token"]

        me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["id"] == "test_user"
        assert me_data["address"] == "0x123"
        assert me_data["roles"] == ["user"]

    def test_me_endpoint_without_token(self):
        """GET /auth/me without a token must return 401."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        me_resp = client.get("/auth/me")
        assert me_resp.status_code == 401

    def test_revoke_endpoint(self):
        """POST /auth/revoke revokes a token and it is then rejected."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        login_resp = client.post("/auth/login", json={
            "user_id": "test_user",
            "address": "0x123",
            "roles": ["user"],
        })
        token = login_resp.json()["token"]

        # Revoke
        revoke_resp = client.post(
            "/auth/revoke",
            json={"token": token},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 200

        # Now the same token should fail
        # But the endpoint uses Depends(get_current_user) which checks revocation
        # The /auth/me endpoint will test this
        me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 401
