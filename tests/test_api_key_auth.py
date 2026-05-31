import hashlib
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from api.middleware.auth import hash_api_key, generate_api_key
from api.models.database import ApiKey


class TestApiKeyHashing:
    def test_hash_api_key_is_sha256(self):
        hashed = hash_api_key("test-key-123")
        assert len(hashed) == 64
        expected = hashlib.sha256(b"test-key-123").hexdigest()
        assert hashed == expected

    def test_hash_api_key_deterministic(self):
        assert hash_api_key("abc") == hash_api_key("abc")

    def test_hash_api_key_different(self):
        assert hash_api_key("key-a") != hash_api_key("key-b")


class TestGenerateApiKey:
    def test_generates_raw_and_hash(self):
        raw, hashed = generate_api_key()
        assert len(raw) == 64
        assert hashed == hash_api_key(raw)

    def test_generates_unique_keys(self):
        keys = [generate_api_key()[0] for _ in range(10)]
        assert len(set(keys)) == 10


class TestApiKeyAuthEndpoints:
    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from api.models.database import get_db
        app = FastAPI()
        from api.routes.auth import router as auth_router
        app.include_router(auth_router)
        return app

    def _setup(self, app, user_override=None):
        from api.routes.auth import get_current_user
        from api.models.database import get_db
        mock_user_callable = lambda: (user_override or {"id": 1, "address": "0xabc", "roles": ["admin"]})
        app.dependency_overrides[get_current_user] = mock_user_callable

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.refresh = MagicMock(side_effect=lambda x: setattr(x, 'id', 1))
        app.dependency_overrides[get_db] = lambda: mock_session
        return mock_session

    def _teardown(self, app):
        app.dependency_overrides.clear()

    def test_create_api_key_requires_auth(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/auth/api-keys")
        assert resp.status_code == 403

    def test_create_api_key_returns_raw_key_once(self, app):
        from fastapi.testclient import TestClient
        from api.routes.auth import generate_api_key
        mock_session = self._setup(app)
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.label = "test-key"
        mock_record.created_at = datetime.utcnow()
        mock_session.refresh = MagicMock(side_effect=lambda x: setattr(x, 'id', 1))

        client = TestClient(app)
        with patch("api.routes.auth.generate_api_key", return_value=("raw-secret-64-chars-lorem-ipsum-dolor", hash_api_key("raw-secret"))):
            resp = client.post("/auth/api-keys?label=test-key")
            assert resp.status_code == 200
            data = resp.json()
            assert data["api_key"] == "raw-secret-64-chars-lorem-ipsum-dolor"
            assert data["label"] == "test-key"
        self._teardown(app)

    def test_list_api_keys(self, app):
        from fastapi.testclient import TestClient
        mock_session = self._setup(app)
        mock_key = ApiKey(id=1, user_id=1, key_hash="abc", label="my-key", created_at=datetime.utcnow())
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_key]

        client = TestClient(app)
        resp = client.get("/auth/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["label"] == "my-key"
        assert data[0]["active"] is True
        self._teardown(app)

    def test_revoke_api_key(self, app):
        from fastapi.testclient import TestClient
        mock_session = self._setup(app)
        mock_key = MagicMock()
        mock_key.id = 1
        mock_key.revoked_at = None
        mock_session.query.return_value.filter.return_value.first.return_value = mock_key

        client = TestClient(app)
        resp = client.delete("/auth/api-keys/1")
        assert resp.status_code == 200
        assert mock_key.revoked_at is not None
        self._teardown(app)

    def test_revoke_nonexistent_key_returns_404(self, app):
        from fastapi.testclient import TestClient
        mock_session = self._setup(app)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        resp = client.delete("/auth/api-keys/999")
        assert resp.status_code == 404
        self._teardown(app)


class TestGetCurrentUserApiKey:
    @pytest.fixture
    def app(self):
        from fastapi import FastAPI, Depends
        from api.middleware.auth import get_current_user
        app = FastAPI()

        @app.get("/test-auth")
        async def test_auth(user=Depends(get_current_user)):
            return user

        return app

    def test_api_key_auth_succeeds_with_valid_key(self, app):
        from fastapi.testclient import TestClient
        from api.middleware.auth import get_db
        client = TestClient(app)

        mock_record = MagicMock()
        mock_record.user_id = 42
        mock_record.id = 1
        mock_record.revoked_at = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_record
        app.dependency_overrides[get_db] = lambda: mock_session

        raw, _ = generate_api_key()
        resp = client.get("/test-auth", headers={"X-API-Key": raw})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 42
        assert data["auth_method"] == "api_key"
        app.dependency_overrides.clear()

    def test_api_key_auth_fails_with_invalid_key(self, app):
        from fastapi.testclient import TestClient
        from api.middleware.auth import get_db
        client = TestClient(app)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: mock_session

        resp = client.get("/test-auth", headers={"X-API-Key": "invalid-key!"})
        assert resp.status_code == 401
        app.dependency_overrides.clear()

    def test_no_auth_returns_403(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/test-auth")
        assert resp.status_code == 403
