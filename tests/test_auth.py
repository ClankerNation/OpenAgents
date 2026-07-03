"""Tests for API key authentication and JWT auth."""
import pytest
import os
import sys

os.environ["JWT_SECRET"] = "test-secret-for-testing-only-32chars!"
os.environ["DATABASE_URL"] = "sqlite:///./test_openagents.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from api.main import app
from api.middleware.auth import (
    generate_api_key,
    verify_api_key,
    _hash_api_key,
    create_access_token,
    create_refresh_token,
)
from api.models.database import init_db, User, SessionLocal, engine, Base


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(id=1, address="0xtest", username="testuser"))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


class TestApiKeyGeneration:
    def test_generate_api_key_format(self):
        full_key, key_hash, key_prefix = generate_api_key()
        assert full_key.startswith("oa_")
        assert len(full_key) > 32
        assert len(key_prefix) == 8
        assert key_prefix.startswith("oa_")

    def test_hash_is_deterministic(self):
        full_key, _, _ = generate_api_key()
        hash1 = _hash_api_key(full_key)
        hash2 = _hash_api_key(full_key)
        assert hash1 == hash2

    def test_verify_valid_key(self):
        full_key, key_hash, _ = generate_api_key()
        assert verify_api_key(full_key, key_hash) is True

    def test_verify_invalid_key(self):
        full_key, key_hash, _ = generate_api_key()
        assert verify_api_key("wrong_key", key_hash) is False

    def test_unique_keys(self):
        keys = set()
        for _ in range(100):
            full_key, _, _ = generate_api_key()
            keys.add(full_key)
        assert len(keys) == 100


class TestApiKeyAuth:
    def test_auth_without_credentials(self):
        response = client.get("/agents")
        assert response.status_code == 401

    def test_auth_with_invalid_api_key(self):
        response = client.get(
            "/agents",
            headers={"X-API-Key": "oa_invalid_key_12345"},
        )
        assert response.status_code == 401

    def test_auth_with_jwt(self):
        token = create_access_token({"sub": "1", "address": "0xtest"})
        response = client.get(
            "/agents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_jwt_invalid_token_type(self):
        token = create_refresh_token({"sub": "1", "address": "0xtest"})
        response = client.get(
            "/agents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_health_unauthenticated(self):
        response = client.get("/health")
        assert response.status_code == 200


class TestApiKeyCRUD:
    def _auth_header(self):
        token = create_access_token({"sub": "1", "address": "0xtest"})
        return {"Authorization": f"Bearer {token}"}

    def test_create_api_key_endpoint(self):
        response = client.post(
            "/auth/api-keys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["full_key"].startswith("oa_")
        assert "will not be shown again" in data["message"]

    def test_list_api_keys(self):
        client.post(
            "/auth/api-keys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        response = client.get(
            "/auth/api-keys",
            headers=self._auth_header(),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0].get("full_key") is None

    def test_revoke_api_key(self):
        create_resp = client.post(
            "/auth/api-keys",
            json={"name": "revoke-test"},
            headers=self._auth_header(),
        )
        assert create_resp.status_code == 201
        key_id = create_resp.json()["id"]
        api_key = create_resp.json()["full_key"]

        revoke_resp = client.delete(
            f"/auth/api-keys/{key_id}",
            headers=self._auth_header(),
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["revoked"] is True

        auth_resp = client.get(
            "/agents",
            headers={"X-API-Key": api_key},
        )
        assert auth_resp.status_code == 401
