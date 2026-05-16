from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.middleware import auth


@pytest.fixture(autouse=True)
def reset_auth_state(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-is-at-least-32-bytes")
    auth.REVOKED_TOKEN_IDS.clear()
    auth.REVOKED_TOKENS.clear()
    yield
    auth.REVOKED_TOKEN_IDS.clear()
    auth.REVOKED_TOKENS.clear()


def test_missing_jwt_secret_fails_closed_without_import_crash(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        auth.create_access_token({"sub": "user-1"})

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "JWT secret is not configured"


def test_decode_rejects_unsigned_none_algorithm_token():
    now = datetime.now(timezone.utc)
    none_token = jwt.encode(
        {
            "sub": "user-1",
            "address": "0xabc",
            "roles": [],
            "type": "access",
            "jti": "unsigned-token",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(none_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_revoked_token_fails_decode():
    token = auth.create_access_token({"sub": "user-1", "address": "0xabc", "roles": ["admin"]})

    assert auth.decode_token(token)["sub"] == "user-1"
    auth.revoke_token(token)

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has been revoked"


def test_refresh_endpoint_issues_new_tokens_and_rejects_reuse():
    client = TestClient(app)
    refresh_token = auth.create_refresh_token(
        {"sub": "user-1", "address": "0xabc", "roles": ["builder"]}
    )

    response = client.post("/auth/refresh", json={"refreshToken": refresh_token})

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["refresh_token"]
    assert body["refreshToken"] == body["refresh_token"]
    assert body["expires_in"] == auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert body["walletAddress"] == "0xabc"
    assert auth.decode_token(body["token"])["type"] == "access"
    assert auth.decode_token(body["refresh_token"])["type"] == "refresh"

    reused_response = client.post("/auth/refresh", json={"refreshToken": refresh_token})

    assert reused_response.status_code == 401
    assert reused_response.json()["detail"] == "Token has been revoked"


def test_revoke_endpoint_accepts_bearer_token_and_blocks_reuse():
    client = TestClient(app)
    token = auth.create_access_token({"sub": "user-1", "address": "0xabc", "roles": []})

    response = client.post("/auth/revoke", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"revoked": True, "type": "access"}

    blocked_response = client.post("/auth/revoke", headers={"Authorization": f"Bearer {token}"})

    assert blocked_response.status_code == 401
    assert blocked_response.json()["detail"] == "Token has been revoked"
