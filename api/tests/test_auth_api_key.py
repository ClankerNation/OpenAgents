import hashlib
import importlib
import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _build_test_client(tmp_path):
    os.environ["JWT_SECRET"] = "test-jwt-secret"
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'auth_test.db').as_posix()}"

    db_mod = importlib.import_module("api.models.database")
    db_mod = importlib.reload(db_mod)

    auth_mod = importlib.import_module("api.middleware.auth")
    auth_mod = importlib.reload(auth_mod)

    auth_routes_mod = importlib.import_module("api.routes.auth")
    auth_routes_mod = importlib.reload(auth_routes_mod)

    db_mod.init_db()

    app = FastAPI()
    app.include_router(auth_routes_mod.router)

    @app.get("/protected")
    async def protected(user=Depends(auth_mod.get_current_user)):
        return user

    return TestClient(app), db_mod, auth_mod


def _create_user(db_mod):
    with db_mod.SessionLocal() as db:
        user = db_mod.User(address="0x1111111111111111111111111111111111111111", username="tester")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def test_jwt_auth_works(tmp_path):
    client, _, auth_mod = _build_test_client(tmp_path)
    token = auth_mod.create_access_token(
        {"sub": "42", "address": "0xabc0000000000000000000000000000000000000", "roles": ["user"]}
    )

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == "42"


def test_api_key_auth_works_and_is_hashed(tmp_path):
    client, db_mod, auth_mod = _build_test_client(tmp_path)
    user_id = _create_user(db_mod)
    token = auth_mod.create_access_token({"sub": str(user_id), "address": "0x1111111111111111111111111111111111111111"})

    create_resp = client.post(
        "/auth/api-keys",
        json={"name": "ci-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200
    payload = create_resp.json()
    raw_key = payload["api_key"]
    key_id = payload["id"]

    with db_mod.SessionLocal() as db:
        key_row = db.query(db_mod.APIKey).filter(db_mod.APIKey.id == key_id).first()
        assert key_row is not None
        assert key_row.key_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        assert key_row.key_hash != raw_key

    protected_resp = client.get("/protected", headers={"X-API-Key": raw_key})
    assert protected_resp.status_code == 200
    assert protected_resp.json()["id"] == str(user_id)


def test_revoked_api_key_fails_auth_immediately(tmp_path):
    client, db_mod, auth_mod = _build_test_client(tmp_path)
    user_id = _create_user(db_mod)
    token = auth_mod.create_access_token({"sub": str(user_id), "address": "0x1111111111111111111111111111111111111111"})

    create_resp = client.post(
        "/auth/api-keys",
        json={"name": "temp-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200
    payload = create_resp.json()
    key_id = payload["id"]
    raw_key = payload["api_key"]

    revoke_resp = client.delete(f"/auth/api-keys/{key_id}", headers={"Authorization": f"Bearer {token}"})
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True

    protected_resp = client.get("/protected", headers={"X-API-Key": raw_key})
    assert protected_resp.status_code == 401
    assert protected_resp.json()["detail"] == "Invalid API key"
