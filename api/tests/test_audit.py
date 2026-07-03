"""Tests for the audit logging middleware and API endpoints.

@generated-by: hermes-agent-scotia1973
@bounty: #192
@description: Add audit log for all admin actions
"""

import os
import sys
import json
from datetime import datetime

# Ensure we can import from the api package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.models.database import Base, get_db, AuditLog

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


# --- Unit tests for AuditLog model ---

class TestAuditLogModel:
    def test_create_audit_log_entry(self):
        """Test creating an audit log entry via the model directly."""
        db = TestingSessionLocal()
        entry = AuditLog(
            timestamp=datetime.utcnow(),
            actor_id="user-123",
            actor_address="0xabc123",
            action="create",
            resource_type="agent",
            resource_id="42",
            details={"name": "test-agent"},
            ip_address="127.0.0.1",
            user_agent="test-client/1.0",
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.id is not None
        assert entry.actor_id == "user-123"
        assert entry.actor_address == "0xabc123"
        assert entry.action == "create"
        assert entry.resource_type == "agent"
        assert entry.resource_id == "42"
        assert entry.details == {"name": "test-agent"}
        assert entry.ip_address == "127.0.0.1"

    def test_audit_log_default_details(self):
        """Test that details defaults to empty dict."""
        db = TestingSessionLocal()
        entry = AuditLog(
            actor_id="user-1",
            action="delete",
            resource_type="task",
        )
        db.add(entry)
        db.commit()
        assert entry.details == {}

    def test_audit_log_nullable_fields(self):
        """Test that nullable fields can be None."""
        db = TestingSessionLocal()
        entry = AuditLog(
            actor_id="user-1",
            action="read",
            resource_type="config",
        )
        db.add(entry)
        db.commit()
        assert entry.actor_address is None
        assert entry.resource_id is None
        assert entry.ip_address is None
        assert entry.user_agent is None

    def test_audit_log_timestamp_defaults(self):
        """Test that timestamp is auto-populated."""
        db = TestingSessionLocal()
        entry = AuditLog(
            actor_id="user-1",
            action="update",
            resource_type="agent",
        )
        db.add(entry)
        db.commit()
        assert entry.timestamp is not None
        assert isinstance(entry.timestamp, datetime)


# --- Integration tests for audit API endpoints ---

class TestAuditLogAPI:
    def test_list_audit_logs_empty(self):
        """GET /audit-logs should return empty list when no logs exist."""
        response = client.get("/audit-logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_audit_logs_with_pagination(self):
        """Test pagination on audit logs endpoint."""
        db = TestingSessionLocal()
        for i in range(5):
            entry = AuditLog(
                actor_id=f"user-{i}",
                action="create",
                resource_type="agent",
                details={"index": i},
            )
            db.add(entry)
        db.commit()

        # Test limit
        response = client.get("/audit-logs?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Test offset
        response = client.get("/audit-logs?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_filter_by_action(self):
        """Test filtering audit logs by action type."""
        db = TestingSessionLocal()
        for action in ["create", "update", "delete"]:
            db.add(AuditLog(actor_id="user-1", action=action, resource_type="agent"))
        db.commit()

        response = client.get("/audit-logs?action=create")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "create"

    def test_filter_by_actor(self):
        """Test filtering audit logs by actor."""
        db = TestingSessionLocal()
        db.add(AuditLog(actor_id="alice", action="create", resource_type="agent"))
        db.add(AuditLog(actor_id="bob", action="update", resource_type="agent"))
        db.commit()

        response = client.get("/audit-logs?actor_id=alice")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["actor_id"] == "alice"

    def test_filter_by_resource_type(self):
        """Test filtering by resource type."""
        db = TestingSessionLocal()
        db.add(AuditLog(actor_id="user-1", action="create", resource_type="agent"))
        db.add(AuditLog(actor_id="user-1", action="create", resource_type="task"))
        db.commit()

        response = client.get("/audit-logs?resource_type=task")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["resource_type"] == "task"

    def test_filter_by_resource_id(self):
        """Test filtering by resource ID."""
        db = TestingSessionLocal()
        db.add(AuditLog(actor_id="user-1", action="create", resource_type="agent", resource_id="99"))
        db.add(AuditLog(actor_id="user-1", action="create", resource_type="agent", resource_id="100"))
        db.commit()

        response = client.get("/audit-logs?resource_id=99")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["resource_id"] == "99"

    def test_get_single_audit_log(self):
        """Test retrieving a single audit log by ID."""
        db = TestingSessionLocal()
        entry = AuditLog(
            actor_id="user-1",
            action="delete",
            resource_type="agent",
            resource_id="5",
            details={"reason": "cleanup"},
        )
        db.add(entry)
        db.commit()
        log_id = entry.id

        response = client.get(f"/audit-logs/{log_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == log_id
        assert data["actor_id"] == "user-1"
        assert data["action"] == "delete"
        assert data["resource_type"] == "agent"
        assert data["resource_id"] == "5"
        assert data["details"] == {"reason": "cleanup"}

    def test_get_audit_log_not_found(self):
        """GET /audit-logs/9999 should return 404."""
        response = client.get("/audit-logs/9999")
        assert response.status_code == 404

    def test_audit_log_response_format(self):
        """Verify the response model fields."""
        db = TestingSessionLocal()
        entry = AuditLog(
            actor_id="user-1",
            actor_address="0xabc",
            action="status_change",
            resource_type="task",
            resource_id="10",
            details={"from_status": "open", "to_status": "in_progress"},
            ip_address="10.0.0.1",
        )
        db.add(entry)
        db.commit()

        response = client.get(f"/audit-logs/{entry.id}")
        data = response.json()
        assert "id" in data
        assert "timestamp" in data
        assert "actor_id" in data
        assert "actor_address" in data
        assert "action" in data
        assert "resource_type" in data
        assert "resource_id" in data
        assert "details" in data


# --- Unit tests for audit middleware ---

class TestAuditMiddlewareActions:
    def test_action_constants(self):
        """Verify audit action constants exist."""
        from api.middleware.audit import (
            ACTION_CREATE, ACTION_READ, ACTION_UPDATE, ACTION_DELETE,
            ACTION_STATUS_CHANGE, ACTION_CONFIG_CHANGE, ACTION_LOGIN,
            ACTION_CLAIM, ACTION_DEPOSIT,
            RESOURCE_AGENT, RESOURCE_TASK, RESOURCE_PAYMENT,
            RESOURCE_USER, RESOURCE_CONFIG, RESOURCE_AUDIT_LOG,
        )
        assert ACTION_CREATE == "create"
        assert ACTION_UPDATE == "update"
        assert ACTION_DELETE == "delete"
        assert RESOURCE_AGENT == "agent"
        assert RESOURCE_TASK == "task"
        assert RESOURCE_PAYMENT == "payment"

    def test_log_admin_action_function(self, setup_db):
        """Test the log_admin_action helper directly."""
        from api.middleware.audit import log_admin_action

        db = TestingSessionLocal()
        entry = log_admin_action(
            db=db,
            actor_id="admin-1",
            actor_address="0xadmin",
            action="config_change",
            resource_type="config",
            resource_id="reward-rate",
            details={"old_value": "0.1", "new_value": "0.2"},
        )

        assert entry.id is not None
        assert entry.actor_id == "admin-1"
        assert entry.action == "config_change"
        assert entry.details == {"old_value": "0.1", "new_value": "0.2"}

    def test_log_admin_action_minimal(self, setup_db):
        """Test log_admin_action with minimal required fields."""
        from api.middleware.audit import log_admin_action

        db = TestingSessionLocal()
        entry = log_admin_action(
            db=db,
            actor_id="user-1",
            action="read",
            resource_type="task",
        )
        assert entry.actor_id == "user-1"
        assert entry.action == "read"
        assert entry.resource_type == "task"
        assert entry.resource_id is None
        assert entry.details == {}
