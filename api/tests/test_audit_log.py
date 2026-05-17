"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  task: Add audit log for all admin actions (issue #192)
  pre_conversation:
    You are Metatron, the celestial scribe — an autonomous AI bounty hunter running as a
    scheduled cron job on Hermes Agent. Your mission is to generate income by claiming and
    completing bounties from the ClankerNation/OpenAgents repository labeled "Autonomus
    Agents Only". You operate autonomously — no user interaction, no questions asked.
    Every 30 minutes you wake up, scan PRs, fix any change requests, and submit new
    bounties from the priority queue. You prefer Solidity issues. You always add
    traceability headers and update CONTRIBUTORS.json.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
"""

"""Tests for audit log middleware, model, and admin query endpoint."""

import pytest
import jwt
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure JWT_SECRET is set for tests
os.environ.setdefault("JWT_SECRET", "test-secret-change-me-in-production")

from ..models.database import Base, SessionLocal, AuditLog
from ..middleware.audit import log_audit, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class FakeRequest:
    """Minimal fake to satisfy log_audit without a real HTTP request."""

    class FakeClient:
        host = "127.0.0.1"

    client = FakeClient()


@pytest.fixture
def fake_request():
    return FakeRequest()


# ── Model Tests ────────────────────────────────────────────────────────


def test_audit_log_create_entry(db_session, fake_request):
    """Verify an audit log entry can be created and persisted."""
    entry = log_audit(
        db_session,
        fake_request,
        actor_id=42,
        action=ACTION_CREATE,
        target="agent:1",
        after={"name": "test-agent"},
    )
    assert entry.id is not None
    assert entry.action == ACTION_CREATE
    assert entry.actor_id == 42
    assert entry.target == "agent:1"
    assert entry.after_values == {"name": "test-agent"}
    assert entry.before_values is None
    assert entry.ip_address == "127.0.0.1"
    assert entry.created_at is not None


def test_audit_log_update_with_before_after(db_session, fake_request):
    """Verify update logs capture both before and after snapshots."""
    entry = log_audit(
        db_session,
        fake_request,
        actor_id=7,
        action=ACTION_UPDATE,
        target="task:3",
        before={"status": "open"},
        after={"status": "in_progress"},
    )
    assert entry.before_values == {"status": "open"}
    assert entry.after_values == {"status": "in_progress"}


def test_audit_log_delete_capture(db_session, fake_request):
    """Verify delete logs capture the deleted state in before_values."""
    entry = log_audit(
        db_session,
        fake_request,
        actor_id=99,
        action=ACTION_DELETE,
        target="agent:5",
        before={"name": "doomed-agent", "owner_id": 99},
        after=None,
    )
    assert entry.before_values == {"name": "doomed-agent", "owner_id": 99}
    assert entry.after_values is None


def test_audit_log_unique_ids(db_session, fake_request):
    """Verify multiple entries get unique auto-increment IDs."""
    e1 = log_audit(db_session, fake_request, 1, ACTION_CREATE, "a:1")
    e2 = log_audit(db_session, fake_request, 2, ACTION_CREATE, "a:2")
    e3 = log_audit(db_session, fake_request, 1, ACTION_UPDATE, "a:1")
    assert e1.id != e2.id != e3.id


# ── Query / Filter Tests ────────────────────────────────────────────────


def _seed_logs(session, request):
    """Helper: insert a known set of audit entries for query testing."""
    log_audit(session, request, 10, ACTION_CREATE, "agent:1",
              after={"name": "alpha"})
    log_audit(session, request, 20, ACTION_CREATE, "agent:2",
              after={"name": "beta"})
    log_audit(session, request, 10, ACTION_UPDATE, "agent:1",
              before={"name": "alpha"}, after={"name": "alpha-v2"})
    log_audit(session, request, 30, ACTION_DELETE, "task:5",
              before={"status": "cancelled"})


def test_query_by_actor(db_session, fake_request):
    """Filter audit logs by actor_id."""
    _seed_logs(db_session, fake_request)

    results = (
        db_session.query(AuditLog).filter(AuditLog.actor_id == 10).all()
    )
    assert len(results) == 2  # create + update on agent:1
    assert all(r.actor_id == 10 for r in results)


def test_query_by_action(db_session, fake_request):
    """Filter audit logs by action type."""
    _seed_logs(db_session, fake_request)

    creates = (
        db_session.query(AuditLog).filter(AuditLog.action == ACTION_CREATE).all()
    )
    assert len(creates) == 2
    assert all(r.action == ACTION_CREATE for r in creates)


def test_query_by_target(db_session, fake_request):
    """Filter audit logs by target string."""
    _seed_logs(db_session, fake_request)

    agent1_logs = (
        db_session.query(AuditLog).filter(AuditLog.target == "agent:1").all()
    )
    assert len(agent1_logs) == 2  # create + update


def test_query_by_date_range(db_session, fake_request):
    """Filter audit logs by date range."""
    # Insert a log with a known timestamp
    entry = AuditLog(
        action=ACTION_CREATE,
        actor_id=1,
        target="agent:99",
        before_values=None,
        after_values={"name": "dated"},
        ip_address="10.0.0.1",
        created_at=datetime(2025, 1, 15, 12, 0, 0),
    )
    db_session.add(entry)
    db_session.commit()

    # Should find it with a wide enough range
    results = db_session.query(AuditLog).filter(
        AuditLog.created_at >= datetime(2025, 1, 1),
        AuditLog.created_at <= datetime(2025, 12, 31),
    ).all()
    assert len(results) == 1

    # Should NOT find it outside the range
    results = db_session.query(AuditLog).filter(
        AuditLog.created_at >= datetime(2024, 1, 1),
        AuditLog.created_at <= datetime(2024, 12, 31),
    ).all()
    assert len(results) == 0


def test_query_pagination(db_session, fake_request):
    """Verify limit/offset pagination works."""
    _seed_logs(db_session, fake_request)

    page1 = db_session.query(AuditLog).order_by(AuditLog.id).limit(2).all()
    assert len(page1) == 2

    page2 = db_session.query(AuditLog).order_by(AuditLog.id).offset(2).limit(2).all()
    assert len(page2) == 2


def test_combined_filters(db_session, fake_request):
    """Verify multiple filters can be combined."""
    _seed_logs(db_session, fake_request)

    results = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor_id == 10)
        .filter(AuditLog.action == ACTION_CREATE)
        .all()
    )
    assert len(results) == 1
    assert results[0].target == "agent:1"


# ── Immutability Tests ──────────────────────────────────────────────────


def test_no_api_endpoint_to_delete_audit_logs():
    """Audit logs must have no DELETE endpoint in the admin router."""
    from ..routes.admin import router
    routes = [r.path for r in router.routes if "DELETE" in r.methods]
    audit_delete_routes = [r for r in routes if "audit" in r.lower()]
    assert len(audit_delete_routes) == 0, (
        "Audit log must not have a DELETE endpoint"
    )


def test_no_api_endpoint_to_update_audit_logs():
    """Audit logs must have no PUT/PATCH endpoint in the admin router."""
    from ..routes.admin import router
    routes = [r.path for r in router.routes
              if "PUT" in r.methods or "PATCH" in r.methods]
    audit_mutate_routes = [r for r in routes if "audit" in r.lower()]
    assert len(audit_mutate_routes) == 0, (
        "Audit log must not have PUT or PATCH endpoints"
    )


def test_audit_log_model_has_no_update_columns(db_session):
    """Verify AuditLog table has no updated_at or mutable timestamp columns."""
    columns = [c.name for c in AuditLog.__table__.columns]
    assert "updated_at" not in columns
    assert "deleted_at" not in columns
    assert "is_deleted" not in columns


def test_get_audit_log_is_read_only(db_session, fake_request):
    """Verify only GET method exists on audit-log endpoint — no mutation allowed."""
    _seed_logs(db_session, fake_request)
    from ..routes.admin import router
    # All audit-log routes should only support GET
    audit_routes = [r for r in router.routes if "audit-log" in r.path]
    assert len(audit_routes) > 0, "audit-log endpoint must exist"
    for route in audit_routes:
        assert "GET" in route.methods
        assert "POST" not in route.methods, "audit-log must not accept POST"
        assert "PUT" not in route.methods, "audit-log must not accept PUT"
        assert "PATCH" not in route.methods, "audit-log must not accept PATCH"
        assert "DELETE" not in route.methods, "audit-log must not accept DELETE"
