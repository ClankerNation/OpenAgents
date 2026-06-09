"""Tests for API key authentication alongside JWT."""

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
    JWT_SECRET, JWT_ALGORITHM,
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
    """Tests for API key creation via POST /auth/api-keys."""

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

    def test_create_api_key_requires_auth(self):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        client = TestClient(main_app)
        response = client.post(
            "/auth/api-keys",
            json={"name": "No Auth Key"},
        )
        assert response.status_code == 401


class TestApiKeyAuth:
    """Tests for authenticating with an API key."""

    def test_api_key_authenticates_successfully(self, sample_user):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)

        # Create an API key
        create_resp = client.post(
            "/auth/api-keys",
            json={"name": "Auth Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 200
        api_key = create_resp.json()["key"]

        # Use the API key to access a protected endpoint
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        response = test_client.get(
            "/protected",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["auth_method"] == "api_key"

    def test_invalid_api_key_rejected(self):
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        response = test_client.get(
            "/protected",
            headers={"X-API-Key": "oa_invalidkey1234567890abcdef"},
        )
        assert response.status_code == 401

    def test_revoked_api_key_rejected(self, sample_user, db_session):
        from api.main import app as main_app
        main_app.dependency_overrides[get_db] = override_get_db
        token = _make_jwt()
        client = TestClient(main_app)

        # Create an API key
        create_resp = client.post(
            "/auth/api-keys",
            json={"name": "Revoke Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 200
        api_key_id = create_resp.json()["id"]

        # Revoke it
        revoke_resp = client.delete(
            f"/auth/api-keys/{api_key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 200

        # Try to use it — should fail
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        api_key = create_resp.json()["key"]
        response = test_client.get(
            "/protected",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


class TestJWTAuth:
    """Tests for JWT authentication (baseline — must still work)."""

    def test_valid_jwt_authenticates(self, sample_user):
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        token = _make_jwt()
        response = test_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["auth_method"] == "jwt"

    def test_expired_jwt_rejected(self):
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        payload = {
            "sub": "1",
            "address": "0x1234567890abcdef",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        response = test_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_no_auth_rejected(self):
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        response = test_client.get("/protected")
        assert response.status_code == 401

    def test_jwt_with_wrong_secret_rejected(self):
        app_test = _make_test_app()
        app_test.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app_test)

        payload = {
            "sub": "1",
            "address": "0x1234567890abcdef",
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        forged_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        response = test_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {forged_token}"},
        )
        assert response.status_code == 401
