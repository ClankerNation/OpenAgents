import os

os.environ["JWT_SECRET"] = "test-secret"

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.middleware.auth import create_access_token, get_current_user, hash_api_key
from api.models.database import ApiKey, Base, User, get_db
from api.routes.auth import router as auth_router


def _build_test_app(db_url: str) -> tuple[FastAPI, sessionmaker]:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return user

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, TestingSessionLocal


def _seed_user(session_local: sessionmaker) -> User:
    db = session_local()
    try:
        user = User(address="0x1111111111111111111111111111111111111111", username="tester")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _jwt_for_user(user: User) -> str:
    return create_access_token({"sub": str(user.id), "address": user.address, "roles": []})


def test_jwt_auth_works(tmp_path):
    app, session_local = _build_test_app(f"sqlite:///{tmp_path / 'jwt.db'}")
    user = _seed_user(session_local)
    token = _jwt_for_user(user)
    client = TestClient(app)

    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user.id
    assert body["auth_method"] == "jwt"


def test_api_key_auth_works_and_is_hashed(tmp_path):
    app, session_local = _build_test_app(f"sqlite:///{tmp_path / 'api-key.db'}")
    user = _seed_user(session_local)
    token = _jwt_for_user(user)
    client = TestClient(app)

    create_resp = client.post(
        "/auth/api-keys",
        json={"name": "ci-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    raw_key = created["api_key"]

    db = session_local()
    try:
        record = db.query(ApiKey).filter(ApiKey.id == created["id"]).first()
        assert record is not None
        assert record.key_hash == hash_api_key(raw_key)
        assert record.key_hash != raw_key
    finally:
        db.close()

    auth_resp = client.get("/protected", headers={"X-API-Key": raw_key})
    assert auth_resp.status_code == 200
    assert auth_resp.json()["auth_method"] == "api_key"


def test_revoked_api_key_fails_immediately(tmp_path):
    app, session_local = _build_test_app(f"sqlite:///{tmp_path / 'revoke.db'}")
    user = _seed_user(session_local)
    token = _jwt_for_user(user)
    client = TestClient(app)

    create_resp = client.post(
        "/auth/api-keys",
        json={"name": "to-revoke"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    raw_key = created["api_key"]
    key_id = created["id"]

    ok_before_revoke = client.get("/protected", headers={"X-API-Key": raw_key})
    assert ok_before_revoke.status_code == 200

    revoke_resp = client.delete(
        f"/auth/api-keys/{key_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoke_resp.status_code == 200

    fail_after_revoke = client.get("/protected", headers={"X-API-Key": raw_key})
    assert fail_after_revoke.status_code == 401
