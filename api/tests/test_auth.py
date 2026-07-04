import os
os.environ["JWT_SECRET"] = "test-secret"
import importlib
import pytest
from fastapi.testclient import TestClient

import api.main as main_module
import api.middleware.auth as auth_module
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_revoked():
    auth_module._revoked_tokens.clear()
    yield
    auth_module._revoked_tokens.clear()


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    auth_module.JWT_SECRET = "test-secret"


def reload_auth():
    importlib.reload(auth_module)
    importlib.reload(main_module)


def test_login_returns_tokens():
    response = client.post(
        "/auth/login",
        json={"user_id": "1", "address": "0xabc", "roles": ["user"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "refresh_token" in data
    assert data["expires_in"] == 3600


def test_missing_jwt_secret_returns_500():
    auth_module.JWT_SECRET = ""
    response = client.post(
        "/auth/login",
        json={"user_id": "1", "address": "0xabc", "roles": ["user"]},
    )
    assert response.status_code == 500
    assert "JWT_SECRET is not configured" in response.json()["detail"]
    auth_module.JWT_SECRET = "test-secret"


def test_refresh_endpoint_returns_new_access_token():
    login = client.post(
        "/auth/login",
        json={"user_id": "1", "address": "0xabc", "roles": ["user"]},
    ).json()
    refresh_resp = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "token" in data
    assert data["expires_in"] == 3600


def test_revoked_token_is_rejected():
    login = client.post(
        "/auth/login",
        json={"user_id": "1", "address": "0xabc", "roles": ["user"]},
    ).json()
    client.post("/auth/revoke", json={"token": login["token"]})
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {login['token']}"})
    assert me_resp.status_code == 401
    assert "revoked" in me_resp.json()["detail"].lower()


def test_none_algorithm_is_rejected():
    import jwt as pyjwt
    payload = {
        "sub": "1",
        "address": "0xabc",
        "roles": ["user"],
        "exp": 9999999999,
        "iat": 1000000000,
        "type": "access",
        "jti": "forged",
    }
    forged = pyjwt.encode(payload, key=None, algorithm="none")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
