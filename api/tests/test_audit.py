"""
Tests for the immutable audit log system.

Covers:
- AuditLog model creation and immutability
- Audit event logging for admin write operations
- GET /admin/audit-log with pagination and filtering
- No DELETE/UPDATE endpoints for audit records
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from ..main import app
from ..models.database import Base, engine, SessionLocal
from ..models.audit import AuditLog

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a clean database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers():
    """Mock admin JWT token for authenticated requests."""
    # In a real test, this would generate a valid JWT. For now, we mock get_current_user.
    return {"Authorization": "Bearer test-admin-token"}


# ── Model Tests ──────────────────────────────────────────────────────────────

def test_audit_log_creation(db_session):
    """AuditLog records can be created with all required fields."""
    entry = AuditLog(
        action="agent.create",
        actor="0x1234...",
        target="agents/new",
        before_values=None,
        after_values={"name": "TestAgent", "model_type": "gpt-4"},
        ip_address="127.0.0.1",
        timestamp=datetime.utcnow(),
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.id is not None
    assert entry.action == "agent.create"
    assert entry.actor == "0x1234..."
    assert entry.after_values["name"] == "TestAgent"


def test_audit_log_immutability(db_session):
    """AuditLog records capture state but have no API update/delete."""
    entry = AuditLog(
        action="task.update",
        actor="0x5678...",
        target="tasks/42",
        before_values={"status": "open"},
        after_values={"status": "completed"},
        timestamp=datetime.utcnow(),
    )
    db_session.add(entry)
    db_session.commit()

    # Verify the record exists and is queryable
    retrieved = db_session.query(AuditLog).filter(AuditLog.id == entry.id).first()
    assert retrieved is not None
    assert retrieved.action == "task.update"

    # Verify there is no DELETE endpoint for audit logs
    response = client.delete(f"/admin/audit-log/{entry.id}")
    assert response.status_code in (404, 405)

    # Verify there is no PUT/PATCH endpoint for audit logs
    response = client.put(f"/admin/audit-log/{entry.id}", json={})
    assert response.status_code in (404, 405)

    response = client.patch(f"/admin/audit-log/{entry.id}", json={})
    assert response.status_code in (404, 405)


# ── Query Tests ──────────────────────────────────────────────────────────────

def create_test_logs(db_session):
    """Helper to seed the database with known audit entries."""
    now = datetime.utcnow()
    entries = [
        AuditLog(
            action="agent.create", actor="0xalice",
            target="agents/new", after_values={"name": "Bot1"},
            timestamp=now - timedelta(hours=2),
        ),
        AuditLog(
            action="agent.update", actor="0xalice",
            target="agents/1",
            before_values={"name": "Bot1"}, after_values={"name": "Bot1-v2"},
            timestamp=now - timedelta(hours=1),
        ),
        AuditLog(
            action="task.create", actor="0xbob",
            target="tasks/new", after_values={"title": "Fix bug", "reward_amount": 100.0},
            timestamp=now - timedelta(minutes=30),
        ),
        AuditLog(
            action="task.update", actor="0xbob",
            target="tasks/1",
            before_values={"status": "open"}, after_values={"status": "completed"},
            timestamp=now - timedelta(minutes=10),
        ),
        AuditLog(
            action="payment.create", actor="0xcharlie",
            target="payments/new", after_values={"amount": 500.0},
            timestamp=now,
        ),
    ]
    for entry in entries:
        db_session.add(entry)
    db_session.commit()
    return entries


def test_query_filter_by_actor(db_session):
    """Filter audit logs by actor."""
    create_test_logs(db_session)

    alice_logs = db_session.query(AuditLog).filter(AuditLog.actor == "0xalice").all()
    assert len(alice_logs) == 2
    assert all(log.actor == "0xalice" for log in alice_logs)

    bob_logs = db_session.query(AuditLog).filter(AuditLog.actor == "0xbob").all()
    assert len(bob_logs) == 2


def test_query_filter_by_action(db_session):
    """Filter audit logs by action type."""
    create_test_logs(db_session)

    create_logs = db_session.query(AuditLog).filter(AuditLog.action.like("%.create")).all()
    assert len(create_logs) == 2  # agent.create + task.create + payment.create = 3

    update_logs = db_session.query(AuditLog).filter(AuditLog.action.like("%.update")).all()
    assert len(update_logs) == 2


def test_query_filter_by_date_range(db_session):
    """Filter audit logs by date range."""
    entries = create_test_logs(db_session)
    now = datetime.utcnow()

    # Query logs from the last 45 minutes
    recent = db_session.query(AuditLog).filter(
        AuditLog.timestamp >= now - timedelta(minutes=45)
    ).all()
    assert len(recent) >= 2  # task.update + payment.create

    # Query logs older than 1.5 hours
    old = db_session.query(AuditLog).filter(
        AuditLog.timestamp <= now - timedelta(hours=1, minutes=30)
    ).all()
    assert len(old) >= 1  # agent.create


def test_query_pagination(db_session):
    """Pagination returns correct page sizes."""
    create_test_logs(db_session)

    page1 = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(2).all()
    page2 = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).offset(2).limit(2).all()

    assert len(page1) == 2
    assert len(page2) == 2
    # No overlap
    ids_p1 = {r.id for r in page1}
    ids_p2 = {r.id for r in page2}
    assert ids_p1.isdisjoint(ids_p2)


def test_empty_query_returns_empty(db_session):
    """Querying for a non-existent actor returns empty results."""
    results = db_session.query(AuditLog).filter(AuditLog.actor == "0xnobody").all()
    assert results == []


# ── API Endpoint Tests ───────────────────────────────────────────────────────

@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_endpoint_requires_admin(mock_require_role, mock_get_user, db_session):
    """GET /admin/audit-log requires admin role."""
    create_test_logs(db_session)

    # Mock admin user
    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    # Test without auth — expect 403 or 401
    response = client.get("/admin/audit-log")
    # Without mocking, this will fail auth. That's expected behavior.
    # The endpoint is correctly gated behind require_role("admin")
    assert response.status_code in (401, 403)


@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_pagination_params(mock_require_role, mock_get_user, db_session):
    """Pagination parameters are enforced on the audit log endpoint."""
    create_test_logs(db_session)

    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    # Test valid pagination
    response = client.get("/admin/audit-log?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["records"]) <= 2


@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_filter_by_actor(mock_require_role, mock_get_user, db_session):
    """Filter audit logs by actor via API."""
    create_test_logs(db_session)

    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    response = client.get("/admin/audit-log?actor=0xalice")
    assert response.status_code == 200
    data = response.json()
    assert all(r["actor"] == "0xalice" for r in data["records"])


@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_filter_by_action(mock_require_role, mock_get_user, db_session):
    """Filter audit logs by action type via API."""
    create_test_logs(db_session)

    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    response = client.get("/admin/audit-log?action=agent.create")
    assert response.status_code == 200
    data = response.json()
    assert all(r["action"] == "agent.create" for r in data["records"])


@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_filter_by_date_range(mock_require_role, mock_get_user, db_session):
    """Filter audit logs by date range via API."""
    create_test_logs(db_session)
    now = datetime.utcnow()

    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    from_iso = (now - timedelta(hours=3)).isoformat()
    to_iso = (now + timedelta(hours=1)).isoformat()

    response = client.get(f"/admin/audit-log?date_from={from_iso}&date_to={to_iso}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3  # Should find most entries


@patch("api.routes.admin.get_current_user")
@patch("api.routes.admin.require_role")
def test_admin_audit_log_no_delete_endpoint(mock_require_role, mock_get_user, db_session):
    """No DELETE endpoint exists for audit log records."""
    mock_user = {"id": "1", "address": "0xadmin", "roles": ["admin"]}
    mock_get_user.return_value = mock_user
    mock_require_role.return_value = lambda: mock_user

    response = client.delete("/admin/audit-log/1")
    assert response.status_code in (404, 405)
