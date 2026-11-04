"""Audit-trail behaviour of the admin endpoints.

@fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04.
@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import os
import pathlib
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.main import app  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402
from api.models.database import (  # noqa: E402
    AUDIT_TRIGGERS, Agent, AuditLog, Base, User, get_db,
)

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for ddl in AUDIT_TRIGGERS:
            conn.exec_driver_sql(ddl)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def auth(roles=("admin",), address="0xadmin"):
    token = create_access_token({"sub": "1", "address": address, "roles": list(roles)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded():
    db = TestingSession()
    owner = User(address="0xowner", username="owner")
    db.add(owner)
    db.commit()
    agent = Agent(name="before-name", description="before-desc", config={"a": 1}, owner_id=owner.id)
    db.add(agent)
    db.commit()
    ids = {"user": owner.id, "agent": agent.id}
    db.close()
    return ids


def audit_rows():
    db = TestingSession()
    rows = db.query(AuditLog).all()
    db.close()
    return rows


def test_admin_update_writes_before_and_after(client, seeded):
    r = client.patch(f"/admin/agents/{seeded['agent']}", json={"name": "after-name"}, headers=auth())
    assert r.status_code == 200, r.text

    rows = audit_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "agent.update"
    assert row.target_type == "agent"
    assert row.target_id == str(seeded["agent"])
    assert row.before["name"] == "before-name"
    assert row.after["name"] == "after-name"
    assert row.actor == "0xadmin"


def test_role_change_is_audited_and_actually_persists(client, seeded):
    r = client.post(f"/admin/users/{seeded['user']}/role", json={"role": "admin"}, headers=auth())
    assert r.status_code == 200, r.text

    rows = audit_rows()
    assert len(rows) == 1
    assert rows[0].action == "user.role"
    assert rows[0].before["roles"] == "user"
    assert rows[0].after["roles"] == "admin"

    db = TestingSession()
    try:
        assert db.query(User).filter(User.id == seeded["user"]).one().roles == "admin"
    finally:
        db.close()


def test_empty_patch_writes_no_row(client, seeded):
    r = client.patch(f"/admin/agents/{seeded['agent']}", json={}, headers=auth())
    assert r.status_code == 400
    assert audit_rows() == []


def test_audit_log_is_paginated_and_filterable(client, seeded):
    for name in ("n1", "n2", "n3"):
        assert client.patch(
            f"/admin/agents/{seeded['agent']}", json={"name": name}, headers=auth()
        ).status_code == 200

    r = client.get("/admin/audit-log", params={"limit": 2}, headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # newest first
    assert body["items"][0]["after"]["name"] == "n3"

    r = client.get("/admin/audit-log", params={"action": "agent.update", "limit": 10}, headers=auth())
    assert r.json()["total"] == 3

    r = client.get("/admin/audit-log", params={"actor": "nobody"}, headers=auth())
    assert r.json()["total"] == 0


def test_non_admin_is_rejected_and_logs_nothing(client, seeded):
    r = client.patch(f"/admin/agents/{seeded['agent']}", json={"name": "x"}, headers=auth(roles=("user",)))
    assert r.status_code == 403
    assert audit_rows() == []


def test_missing_agent_404(client):
    r = client.patch("/admin/agents/9999", json={"name": "x"}, headers=auth())
    assert r.status_code == 404
    assert audit_rows() == []


def test_rows_are_immutable_object_path(seeded, client):
    client.patch(f"/admin/agents/{seeded['agent']}", json={"name": "keep"}, headers=auth())

    db = TestingSession()
    try:
        row = db.query(AuditLog).first()
        row.action = "tampered"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
    finally:
        db.rollback()
        db.close()

    db = TestingSession()
    try:
        row = db.query(AuditLog).first()
        db.delete(row)
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
    finally:
        db.close()


def test_rows_are_immutable_bulk_path(seeded, client):
    """ORM events miss bulk statements; the database trigger is what stops these."""
    client.patch(f"/admin/agents/{seeded['agent']}", json={"name": "keep"}, headers=auth())

    db = TestingSession()
    try:
        with pytest.raises(Exception, match="append-only"):
            db.execute(update(AuditLog).values(action="tampered"))
            db.commit()
    finally:
        db.rollback()
        db.close()

    db = TestingSession()
    try:
        with pytest.raises(Exception, match="append-only"):
            db.query(AuditLog).delete()
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_audit_log_limits_page_size(client):
    r = client.get("/admin/audit-log", params={"limit": 500}, headers=auth())
    assert r.status_code == 422
