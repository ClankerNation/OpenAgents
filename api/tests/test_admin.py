"""Tests for admin audit log endpoints — immutability, queries, pagination."""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.models.database import Base, get_db, AuditLog
from api.routes.admin import router as admin_router, log_admin_action

# In-memory SQLite with StaticPool so all connections share the same DB
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Build test app
test_app = FastAPI()
test_app.include_router(admin_router)
test_app.dependency_overrides[get_db] = override_get_db

client = TestClient(test_app)


@pytest.fixture(autouse=True)
def setup_db():
    """Recreate tables before each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_audit_log():
    """POST /admin/audit-log should create an entry and return 201."""
    payload = {
        "action": "user_suspend",
        "actor": "admin-1",
        "target": "user-42",
        "before_value": {"status": "active"},
        "after_value": {"status": "suspended"},
        "ip_address": "10.0.0.1",
    }
    resp = client.post("/admin/audit-log", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["action"] == "user_suspend"
    assert data["actor"] == "admin-1"
    assert data["target"] == "user-42"
    assert data["before_value"] == {"status": "active"}
    assert data["after_value"] == {"status": "suspended"}
    assert data["ip_address"] == "10.0.0.1"
    assert "id" in data
    assert "created_at" in data


def test_query_by_actor():
    """GET /admin/audit-log?actor=... should filter to that actor."""
    db = TestSessionLocal()
    log_admin_action(db, "create_task", "alice", "task-1")
    log_admin_action(db, "create_task", "bob", "task-2")
    log_admin_action(db, "delete_task", "alice", "task-3")
    db.close()

    resp = client.get("/admin/audit-log?actor=alice")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 2
    for entry in results:
        assert entry["actor"] == "alice"


def test_query_by_action():
    """GET /admin/audit-log?action=... should filter to that action."""
    db = TestSessionLocal()
    log_admin_action(db, "create_task", "admin-1", "task-1")
    log_admin_action(db, "delete_task", "admin-1", "task-2")
    log_admin_action(db, "create_task", "admin-2", "task-3")
    db.close()

    resp = client.get("/admin/audit-log?action=create_task")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 2
    for entry in results:
        assert entry["action"] == "create_task"


def test_query_by_date_range():
    """GET with date_from/date_to should return entries within range."""
    now = datetime.utcnow()
    db = TestSessionLocal()

    entry1 = AuditLog(action="test", actor="a", created_at=now - timedelta(days=10))
    entry2 = AuditLog(action="test", actor="a", created_at=now - timedelta(days=3))
    entry3 = AuditLog(action="test", actor="a", created_at=now + timedelta(days=1))
    db.add_all([entry1, entry2, entry3])
    db.commit()
    db.close()

    from_str = (now - timedelta(days=5)).isoformat()
    resp = client.get(f"/admin/audit-log?date_from={from_str}")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 2


def test_pagination():
    """skip/limit should paginate correctly."""
    db = TestSessionLocal()
    for i in range(10):
        log_admin_action(db, f"action_{i}", "tester", f"target_{i}")
    db.close()

    resp = client.get("/admin/audit-log?skip=0&limit=3")
    assert resp.status_code == 200
    page1 = resp.json()
    assert len(page1) == 3

    resp = client.get("/admin/audit-log?skip=3&limit=3")
    page2 = resp.json()
    assert len(page2) == 3

    resp = client.get("/admin/audit-log?skip=9&limit=3")
    page4 = resp.json()
    assert len(page4) == 1

    ids_page1 = {e["id"] for e in page1}
    ids_page2 = {e["id"] for e in page2}
    assert ids_page1.isdisjoint(ids_page2)


def test_immutable_no_delete():
    """DELETE /admin/audit-log should return 405 Method Not Allowed."""
    resp = client.delete("/admin/audit-log")
    assert resp.status_code == 405

    resp = client.delete("/admin/audit-log/1")
    assert resp.status_code in (405, 404)


def test_immutable_no_update():
    """PUT and PATCH /admin/audit-log should return 405 (no endpoint)."""
    resp = client.put("/admin/audit-log/1", json={"action": "hacked"})
    assert resp.status_code in (405, 404)

    resp = client.patch("/admin/audit-log/1", json={"action": "hacked"})
    assert resp.status_code in (405, 404)
