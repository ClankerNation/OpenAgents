@generated-by: opencode
@platform: OpenCode (opencode.ai)
@timestamp: 2026-07-05T00:00:00+05:30
@session: This file was modified as part of the OpenAgents bounty program. All startup configuration and instructions are documented per project convention.
"

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.main import app
from api.middleware.audit import log_action, get_audit_logs, clear_audit_logs


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_audit_logs():
    clear_audit_logs()
    yield
    clear_audit_logs()


def test_log_action_creates_entry():
    log_action(actor="0xabc", action="create_agent", target="agent:1")
    logs = get_audit_logs()
    assert len(logs) == 1
    entry = logs[0]
    assert entry["actor"] == "0xabc"
    assert entry["action"] == "create_agent"
    assert entry["target"] == "agent:1"
    assert "timestamp" in entry
    assert entry["metadata"] == {}
    assert entry["before"] is None
    assert entry["after"] is None


def test_log_action_with_optional_fields():
    log_action(
        actor=None,
        action="delete_agent",
        target="agent:2",
        ip="127.0.0.1",
        user_agent="test-client",
        metadata={"note": "admin action"},
    )
    logs = get_audit_logs(limit=10)
    assert len(logs) == 1
    entry = logs[0]
    assert entry["actor"] is None
    assert entry["ip"] == "127.0.0.1"
    assert entry["user_agent"] == "test-client"
    assert entry["metadata"]["note"] == "admin action"


def test_log_action_with_before_after():
    log_action(
        actor="0xadmin",
        action="update_agent",
        target="agent:5",
        before={"name": "old-name", "active": True},
        after={"name": "new-name", "active": False},
    )
    logs = get_audit_logs()
    assert len(logs) == 1
    entry = logs[0]
    assert entry["before"] == {"name": "old-name", "active": True}
    assert entry["after"] == {"name": "new-name", "active": False}


def test_get_audit_logs_returns_reversed_order():
    log_action(actor="u1", action="a1", target="t1")
    log_action(actor="u2", action="a2", target="t2")
    logs = get_audit_logs(limit=10)
    assert logs[0]["action"] == "a2"
    assert logs[1]["action"] == "a1"


def test_audit_log_endpoint():
    log_action(actor="0xabc", action="create_agent", target="agent:1")
    response = client.get("/admin/audit-log?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert len(data["entries"]) == 1
    assert data["entries"][0]["actor"] == "0xabc"


def test_audit_log_endpoint_default_limit():
    for _ in range(5):
        log_action(actor="test", action="x", target="t")
    response = client.get("/admin/audit-log")
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 5


def test_clear_audit_logs():
    log_action(actor="u", action="a", target="t")
    assert len(get_audit_logs()) == 1
    clear_audit_logs()
    assert len(get_audit_logs()) == 0