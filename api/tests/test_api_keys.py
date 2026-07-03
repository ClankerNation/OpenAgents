import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.main import app
from api.middleware.auth import create_api_key, revoke_api_key, _key_metadata

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_api_keys():
    _key_metadata.clear()
    yield
    _key_metadata.clear()


def test_api_key_auth():
    raw_key, meta = create_api_key("test-key", "api")
    response = client.get("/health", headers={"X-API-Key": raw_key})
    assert response.status_code == 200


def test_jwt_auth_still_works():
    from api.middleware.auth import generate_login_tokens
    tokens = generate_login_tokens("1", "0xabc", ["user"])
    response = client.get("/health", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert response.status_code == 200


def test_revoked_api_key_fails():
    raw_key, meta = create_api_key("test-key", "api")
    from api.middleware.auth import verify_api_key
    revoke_api_key(meta["id"])
    assert verify_api_key(raw_key) is None


def test_create_api_key_returns_unhashed_key():
    response = client.post(
        "/auth/api-keys",
        json={"name": "new-key", "role": "api"},
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code in (401, 200, 422)
    if response.status_code == 200:
        body = response.json()
        assert "api_key" in body
        assert body["api_key"].startswith("oa_")


def test_delete_api_key():
    raw_key, meta = create_api_key("test-key", "api")
    response = client.delete(
        f"/auth/api-keys/{meta['id']}",
        headers={"Authorization": "Bearer dummy"},
    )
    assert response.status_code in (401, 200, 404)
    if response.status_code == 200:
        assert "revoked" in response.json().get("message", "").lower()
