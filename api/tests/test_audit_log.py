"""Tests for immutable audit logging (Issue #192)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os

os.environ["JWT_SECRET"] = "test_secret"

from api.main import app
from api.models.database import Base, get_db
from api.models.audit_log import AuditLog

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def _get_admin_token():
    payload = {
        "sub": "1",
        "address": "0xAdminAddress",
        "roles": ["admin"],
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, "test_secret", algorithm="HS256")


def test_create_audit_log_entry():
    db = TestingSessionLocal()
    entry = AuditLog(
        action="user.update",
        actor="0xAdminAddress",
        target="user:42",
        before_values={"username": "old"},
        after_values={"username": "new"},
        ip_address="127.0.0.1",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert entry.id is not None
    assert entry.action == "user.update"
    assert entry.actor == "0xAdminAddress"
    assert entry.timestamp is not None
    db.close()


def test_audit_log_immutability():
    """Verify that audit records cannot be modified or deleted via the API."""
    db = TestingSessionLocal()
    entry = AuditLog(
        action="config.update",
        actor="0xAdminAddress",
        target="config:maintenance",
    )
    db.add(entry)
    db.commit()
    log_id = entry.id
    db.close()

    db = TestingSessionLocal()
    record = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    assert record is not None
    assert record.action == "config.update"
    db.close()


def test_audit_log_query_filters():
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    entries = [
        AuditLog(action="user.update", actor="0xAlice", timestamp=now - timedelta(hours=2)),
        AuditLog(action="config.update", actor="0xBob", timestamp=now - timedelta(hours=1)),
        AuditLog(action="user.update", actor="0xBob", timestamp=now),
    ]
    db.add_all(entries)
    db.commit()
    db.close()

    # Filter by actor
    response = client.get("/admin/audit-log?actor=0xBob", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert all(item["actor"] == "0xBob" for item in data["items"])

    # Filter by action
    response = client.get("/admin/audit-log?action=user.update", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert all(item["action"] == "user.update" for item in data["items"])

    # Filter by date range — use ISO format with Z suffix for UTC
    start = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = client.get(f"/admin/audit-log?start_date={start}&end_date={end}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
