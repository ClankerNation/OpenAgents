"""Tests for JWT and API-key authentication.

Contributor: Codex for charlie12520.
Runtime instructions: private platform instructions are intentionally not disclosed.
Environment: Windows x64, PowerShell, C:/Users/charl/Desktop/AI STUFF/ten_buck_attempt/repos/OpenAgents.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-with-at-least-32-bytes")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.middleware.auth import create_access_token, get_current_user
from api.middleware.ratelimit import (
    RateLimitConfig,
    RateLimitMiddleware,
    _request_counts,
)
from api.models.database import ApiKey, Base, User, get_db
from api.routes.auth import router as auth_router


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add(User(id=1, address="0x1111111111111111111111111111111111111111"))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return user

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def auth_header():
    token = create_access_token(
        {
            "sub": "1",
            "address": "0x1111111111111111111111111111111111111111",
            "roles": ["agent"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_jwt_auth_still_works():
    client, _ = build_client()

    response = client.get("/protected", headers=auth_header())

    assert response.status_code == 200
    assert response.json()["id"] == "1"
    assert response.json()["auth_method"] == "jwt"


def test_api_key_generation_stores_hash_and_authenticates():
    client, SessionLocal = build_client()

    created = client.post(
        "/auth/api-keys",
        headers=auth_header(),
        json={"name": "ci-key"},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["key"].startswith("oa_")

    with SessionLocal() as db:
        api_key = db.query(ApiKey).filter(ApiKey.id == body["id"]).one()
        assert api_key.key_hash != body["key"]
        assert len(api_key.key_hash) == 64

    response = client.get("/protected", headers={"X-API-Key": body["key"]})

    assert response.status_code == 200
    assert response.json()["id"] == "1"
    assert response.json()["auth_method"] == "api_key"
    assert response.json()["api_key_id"] == body["id"]


def test_revoked_api_key_fails_immediately():
    client, _ = build_client()
    created = client.post(
        "/auth/api-keys",
        headers=auth_header(),
        json={"name": "temporary-key"},
    ).json()

    revoked = client.delete(f"/auth/api-keys/{created['id']}", headers=auth_header())

    assert revoked.status_code == 200
    assert revoked.json() == {"id": created["id"], "revoked": True}

    response = client.get("/protected", headers={"X-API-Key": created["key"]})

    assert response.status_code == 401


def test_api_key_cannot_manage_api_keys():
    client, _ = build_client()
    created = client.post(
        "/auth/api-keys",
        headers=auth_header(),
        json={"name": "integration-key"},
    ).json()

    response = client.post(
        "/auth/api-keys",
        headers={"X-API-Key": created["key"]},
        json={"name": "nested-key"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "JWT authentication required"


def test_rate_limit_buckets_differ_for_api_key_jwt_and_anonymous_traffic():
    _request_counts.clear()

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(requests_per_window=2, window_seconds=60),
    )

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    client = TestClient(app)

    anonymous_headers = {"X-Forwarded-For": "198.51.100.10"}
    jwt_headers = {
        "Authorization": "Bearer placeholder",
        "X-Forwarded-For": "198.51.100.20",
    }
    api_key_headers = {"X-API-Key": "oa_test_key"}

    assert client.get("/limited", headers=anonymous_headers).status_code == 200
    assert client.get("/limited", headers=anonymous_headers).status_code == 429

    for _ in range(2):
        assert client.get("/limited", headers=jwt_headers).status_code == 200
    assert client.get("/limited", headers=jwt_headers).status_code == 429

    for _ in range(6):
        assert client.get("/limited", headers=api_key_headers).status_code == 200
    assert client.get("/limited", headers=api_key_headers).status_code == 429
