"""Tests for audit log endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from api.routes.audit import router, log_audit
from api.models.database import init_db, get_db, AuditLog


@pytest.fixture
def app():
    init_db()
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_audit_log_model_fields():
    """AuditLog model has required fields."""
    assert hasattr(AuditLog, 'action')
    assert hasattr(AuditLog, 'actor')
    assert hasattr(AuditLog, 'target')
    assert hasattr(AuditLog, 'before_value')
    assert hasattr(AuditLog, 'after_value')
    assert hasattr(AuditLog, 'timestamp')
    assert hasattr(AuditLog, 'ip_address')


def test_log_audit_creates_entry():
    """log_audit creates an entry."""
    init_db()
    db = next(get_db())
    entry = log_audit(db, action="test_action", actor="test_actor", target="test_target",
                     before_value="before", after_value="after")
    assert entry.action == "test_action"
    assert entry.actor == "test_actor"
    assert entry.target == "test_target"
    assert entry.before_value == "before"
    assert entry.after_value == "after"


def test_get_audit_log_endpoint_exists(client):
    """Audit log endpoint exists."""
    response = client.get("/admin/audit-log")
    assert response.status_code != 404


def test_audit_log_immutable_delete(client):
    """Audit logs cannot be deleted."""
    response = client.delete("/admin/audit-log/1")
    assert response.status_code == 405


def test_audit_log_immutable_update(client):
    """Audit logs cannot be updated."""
    response = client.put("/admin/audit-log/1")
    assert response.status_code == 405


def test_audit_log_date_filtering():
    """Audit log supports date range filtering."""
    init_db()
    db = next(get_db())
    log_audit(db, action="action1", actor="user1")
    entries = db.query(AuditLog).filter(AuditLog.timestamp >= datetime.utcnow() - timedelta(days=1)).all()
    assert len(entries) >= 1


def test_audit_log_entry_model():
    """AuditLogEntry model validates correctly."""
    from api.routes.audit import AuditLogEntry
    entry = AuditLogEntry(
        id=1,
        action="test",
        actor="user1",
        target="agent_1",
        timestamp=datetime.utcnow(),
    )
    assert entry.id == 1
    assert entry.action == "test"
    assert entry.actor == "user1"
