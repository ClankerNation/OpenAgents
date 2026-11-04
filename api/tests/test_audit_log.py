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
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.main import app  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402
from api.models.database import Base, Agent, AuditLog, User, get_db  # noqa: E402

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


def test_role_change_is_audited(client, seeded):
    r = client.post(f"/admin/users/{seeded['user']}/role", json={"role": "admin"}, headers=auth())
    assert r.status_code == 200, r.text
    rows = audit_rows()
    assert rows[0].action == "user.role"
    assert rows[0].after["requested_role"] == "admin"


def test_audit_log_is_paginated_and_filterable(client, seeded):
    for name in ("n1", "n2", "n3"):
        client.patch(f"/admin/agents/{seeded['agent']}", json={"name": name}, headers=auth())

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


def test_rows_are_immutable(seeded, client):
    client.patch(f"/admin/agents/{seeded['agent']}", json={"name": "keep"}, headers=auth())

    db = TestingSession()
    row = db.query(AuditLog).first()
    row.action = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()

    db = TestingSession()
    row = db.query(AuditLog).first()
    db.delete(row)
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.close()


def test_audit_log_limits_page_size(client):
    r = client.get("/admin/audit-log", params={"limit": 500}, headers=auth())
    assert r.status_code == 422
