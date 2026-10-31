"""Tests for audit log endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import datetime

from api.routes.audit import router, log_audit


@pytest.fixture
def app():
    from api.models.database import init_db
    init_db()
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_audit_log_model():
    """AuditLog model fields exist."""
    from api.models.database import AuditLog
    assert hasattr(AuditLog, 'action')
    assert hasattr(AuditLog, 'actor')
    assert hasattr(AuditLog, 'target')
    assert hasattr(AuditLog, 'before_value')
    assert hasattr(AuditLog, 'after_value')
    assert hasattr(AuditLog, 'timestamp')
    assert hasattr(AuditLog, 'ip_address')


def test_log_audit_function():
    """log_audit creates an entry."""
    from api.models.database import init_db, get_db
    init_db()
    db = next(get_db())
    entry = log_audit(db, action="test_action", actor="test_actor", target="test_target")
    assert entry.action == "test_action"
    assert entry.actor == "test_actor"
    assert entry.target == "test_target"


def test_get_audit_log_endpoint_exists(client):
    """Audit log endpoint exists."""
    response = client.get("/admin/audit-log")
    # Should not be 404
    assert response.status_code != 404


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
