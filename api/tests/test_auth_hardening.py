import importlib
import os
import sys

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def load_auth(monkeypatch, secret="test-secret-with-enough-entropy-123", environment="development"):
    if secret is None:
        monkeypatch.delenv("JWT_SECRET", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("APP_ENV", environment)
    sys.modules.pop("api.middleware.auth", None)
    return importlib.import_module("api.middleware.auth")


def test_rejects_none_algorithm_tokens(monkeypatch):
    auth = load_auth(monkeypatch)
    unsigned = jwt.encode(
        {"sub": "1", "address": "0xabc", "type": "access"},
        key="",
        algorithm="none",
    )

    with pytest.raises(Exception) as exc:
        auth.decode_token(unsigned)

    assert getattr(exc.value, "status_code", None) == 401


def test_missing_secret_uses_development_fallback(monkeypatch):
    auth = load_auth(monkeypatch, secret=None, environment="development")

    token = auth.create_access_token({"sub": "1", "address": "0xabc"})
    payload = auth.decode_token(token)

    assert payload["sub"] == "1"


def test_missing_secret_errors_in_production(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    sys.modules.pop("api.middleware.auth", None)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        importlib.import_module("api.middleware.auth")


def test_revoked_token_fails(monkeypatch):
    auth = load_auth(monkeypatch)
    token = auth.create_access_token({"sub": "1", "address": "0xabc"})
    payload = auth.decode_token(token)
    auth.revoked_tokens.add(payload["jti"])

    with pytest.raises(Exception) as exc:
        auth.decode_token(token)

    assert getattr(exc.value, "status_code", None) == 401
    assert "revoked" in exc.value.detail


def test_refresh_endpoint_returns_new_access_token(monkeypatch):
    auth = load_auth(monkeypatch)
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    refresh_token = auth.create_refresh_token({
        "sub": "1",
        "address": "0xabc",
        "roles": ["agent"],
    })

    response = client.post("/auth/refresh", params={"refresh_token": refresh_token})

    assert response.status_code == 200
    payload = auth.decode_token(response.json()["token"])
    assert payload["type"] == "access"
    assert payload["sub"] == "1"
    assert payload["roles"] == ["agent"]
