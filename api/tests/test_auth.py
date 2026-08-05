import os
import subprocess
import sys

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.middleware import auth
from api.main import app


@pytest.fixture(autouse=True)
def clear_revoked_tokens():
    auth.revoked_tokens.clear()
    yield
    auth.revoked_tokens.clear()


def test_none_algorithm_is_rejected():
    token = jwt.encode(
        {"sub": "agent", "type": "access"},
        key="",
        algorithm="none",
    )

    with pytest.raises(HTTPException) as error:
        auth.decode_token(token)

    assert error.value.status_code == 401


def test_missing_secret_does_not_crash_import():
    environment = os.environ.copy()
    environment.pop("JWT_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", "import api.middleware.auth"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_revoked_access_token_is_rejected():
    tokens = auth.generate_login_tokens("agent-1", "0xabc")
    assert auth.decode_token(tokens["token"])["sub"] == "agent-1"

    auth.revoke_token(tokens["token"])

    with pytest.raises(HTTPException) as error:
        auth.decode_token(tokens["token"])
    assert error.value.status_code == 401


def test_refresh_requires_refresh_token_and_issues_access_token():
    tokens = auth.generate_login_tokens("agent-1", "0xabc", ["solver"])
    refreshed = auth.refresh_access_token(tokens["refresh_token"])
    payload = auth.decode_token(refreshed["token"])

    assert payload["type"] == "access"
    assert payload["sub"] == "agent-1"
    assert payload["roles"] == ["solver"]

    with pytest.raises(HTTPException) as error:
        auth.refresh_access_token(tokens["token"])
    assert error.value.status_code == 401


def test_auth_endpoints_refresh_and_revoke():
    tokens = auth.generate_login_tokens("agent-1", "0xabc")
    client = TestClient(app)

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["token"]

    revoke_response = client.post(
        "/auth/revoke",
        json={"token": tokens["token"]},
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json() == {"revoked": True}
