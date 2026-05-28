"""Tests for API key authentication."""

import pytest
import sys
import os
import jwt
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.models.database as db_module
from api.models.database import Base, get_db, ApiKey, User
from api.middleware.auth import (
    hash_api_key, generate_api_key, get_current_user,
    JWT_SECRET, JWT_ALGORITHM, _authenticate_api_key,
)

TEST_DATABASE_URL = "sqlite:///./test_apikey.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    # Patch the module-level get_db so auth middleware uses test DB
    original = db_module.get_db
    db_module.get_db = override_get_db
    yield
    db_module.get_db = original
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_user(db_session):
    user = User(id=1, address="0x1234567890abcdef", username="testuser")
    db_session.add(user)
    db_session.commit()
    return user


def _make_test_app():
    test_app = FastAPI()
    test_app.dependency_overrides[get_db] = override_get_db

    @test_app.get("/public")
    async def public():
        return {"ok": True}

    @test_app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return {"user_id": user["id"], "auth_method": user.get("auth_method")}

    return test_app


def _make_jwt(user_id: str = "1") -> str:
    payload = {
        "sub": user_id,
        "address": "0x1234567890abcdef",
        "roles": [],
        "type": "access",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class TestApiKeyCreation:
    def test_create_api_key(self, sample_user):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)
        response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"].startswith("oa_")
        assert len(data["key"]) == 67
        assert data["name"] == "Test Key"

    def test_create_requires_auth(self):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        client = TestClient(main_app)
        response = client.post("/auth/api-keys", json={"name": "Test"})
        assert response.status_code == 401


class TestApiKeyAuthentication:
    def test_api_key_auth_works(self, sample_user, db_session):
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = ApiKey(
            user_id="1", key_hash=key_hash,
            name="Test Key", created_at=datetime.utcnow(),
        )
        db_session.add(api_key)
        db_session.commit()

        test_app = _make_test_app()
        client = TestClient(test_app)
        response = client.get("/protected", headers={"X-API-Key": raw_key})
        assert response.status_code == 200
        data = response.json()
        assert data["auth_method"] == "api_key"

    def test_invalid_api_key_rejected(self):
        test_app = _make_test_app()
        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/protected", headers={"X-API-Key": "oa_invalid"})
        assert response.status_code == 401

    def test_revoked_api_key_rejected(self, sample_user, db_session):
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = ApiKey(
            user_id="1", key_hash=key_hash,
            name="Revoked Key", revoked=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(api_key)
        db_session.commit()

        test_app = _make_test_app()
        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/protected", headers={"X-API-Key": raw_key})
        assert response.status_code == 401

    def test_jwt_still_works(self, sample_user):
        test_app = _make_test_app()
        token = _make_jwt()
        client = TestClient(test_app)
        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["auth_method"] == "jwt"

    def test_no_auth_rejected(self):
        test_app = _make_test_app()
        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/protected")
        assert response.status_code == 401


class TestApiKeyRevocation:
    def test_revoke_api_key(self, sample_user, db_session):
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = ApiKey(
            user_id="1", key_hash=key_hash,
            name="To Revoke", created_at=datetime.utcnow(),
        )
        db_session.add(api_key)
        db_session.commit()
        key_id = api_key.id

        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)
        response = client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["revoked"] is True

        test_app = _make_test_app()
        test_client = TestClient(test_app, raise_server_exceptions=False)
        response = test_client.get("/protected", headers={"X-API-Key": raw_key})
        assert response.status_code == 401

    def test_revoke_nonexistent_key(self, sample_user):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)
        response = client.delete(
            "/auth/api-keys/999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestApiKeyListing:
    def test_list_api_keys(self, sample_user, db_session):
        for i in range(3):
            key = ApiKey(
                user_id="1", key_hash=hash_api_key(f"key_{i}"),
                name=f"Key {i}", created_at=datetime.utcnow(),
            )
            db_session.add(key)
        db_session.commit()

        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)
        response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_excludes_revoked(self, sample_user, db_session):
        for i in range(3):
            key = ApiKey(
                user_id="1", key_hash=hash_api_key(f"key_{i}"),
                name=f"Key {i}", revoked=(i == 0),
                created_at=datetime.utcnow(),
            )
            db_session.add(key)
        db_session.commit()

        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)
        response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
