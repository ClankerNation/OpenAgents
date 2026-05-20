import importlib

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.middleware.auth as auth
from api.main import app


def configure_secret(monkeypatch, value="test-secret"):
    monkeypatch.setenv("JWT_SECRET", value)
    reloaded = importlib.reload(auth)
    return reloaded


def test_none_algorithm_is_rejected(monkeypatch):
    auth_module = configure_secret(monkeypatch)
    token = jwt.encode({"sub": "1", "type": "access"}, key="", algorithm="none")

    with pytest.raises(HTTPException) as exc:
        auth_module.decode_token(token)

    assert exc.value.status_code == 401
    assert "algorithm" in exc.value.detail


def test_missing_secret_errors_without_import_crash(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    auth_module = importlib.reload(auth)

    with pytest.raises(HTTPException) as exc:
        auth_module.create_access_token({"sub": "1"})

    assert exc.value.status_code == 500
    assert "JWT_SECRET" in exc.value.detail


def test_revoked_tokens_fail(monkeypatch):
    auth_module = configure_secret(monkeypatch)
    token = auth_module.create_access_token({"sub": "1", "address": "0xabc"})

    auth_module.revoke_token(token)

    with pytest.raises(HTTPException) as exc:
        auth_module.decode_token(token)

    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail


def test_refresh_endpoint_returns_new_access_token(monkeypatch):
    auth_module = configure_secret(monkeypatch)
    refresh_token = auth_module.create_refresh_token({"sub": "1", "address": "0xabc", "roles": ["agent"]})
    client = TestClient(app)

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    data = response.json()
    assert data["token"]
    payload = auth_module.decode_token(data["token"])
    assert payload["type"] == "access"
    assert payload["sub"] == "1"
