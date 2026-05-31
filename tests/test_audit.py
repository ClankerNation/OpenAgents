import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import MagicMock, patch

from api.middleware.audit import record_audit_log, ADMIN_ACTIONS, is_admin_action
from api.models.database import AuditLog


class TestAdminActions:
    def test_is_admin_action_delete_user(self):
        assert is_admin_action("DELETE", "/users/123") == "user.delete"

    def test_is_admin_action_delete_agent(self):
        assert is_admin_action("DELETE", "/agents/456") == "agent.delete"

    def test_is_admin_action_admin_post(self):
        assert is_admin_action("POST", "/admin/escrow/release") == "escrow.release"

    def test_is_admin_action_status_patch(self):
        assert is_admin_action("PATCH", "/tasks/1/status") == "task.force_complete"

    def test_is_admin_action_returns_none(self):
        assert is_admin_action("GET", "/tasks") is None
        assert is_admin_action("POST", "/agents") is None

    def test_admin_actions_set(self):
        assert "user.delete" in ADMIN_ACTIONS
        assert "admin.grant" in ADMIN_ACTIONS
        assert "task.force_complete" in ADMIN_ACTIONS


class TestRecordAuditLog:
    def test_record_audit_log(self):
        db = MagicMock()
        record_audit_log(
            db=db,
            action="user.delete",
            resource_type="user",
            resource_id="42",
            admin_id=1,
            admin_address="0xabc",
            details={"reason": "spam"},
            ip_address="127.0.0.1",
            success=True,
        )
        db.add.assert_called_once()
        log = db.add.call_args[0][0]
        assert log.action == "user.delete"
        assert log.resource_type == "user"
        assert log.resource_id == "42"
        assert log.admin_id == 1
        assert log.admin_address == "0xabc"
        assert log.details == {"reason": "spam"}
        assert log.ip_address == "127.0.0.1"
        assert log.success == 1
        db.commit.assert_called_once()

    def test_record_audit_log_minimal(self):
        db = MagicMock()
        record_audit_log(
            db=db,
            action="config.update",
            resource_type="config",
        )
        log = db.add.call_args[0][0]
        assert log.action == "config.update"
        assert log.details is None
        assert log.ip_address is None


class TestAuditAPI:
    @pytest.fixture
    def app(self):
        app = FastAPI()
        from api.routes.admin import router
        app.include_router(router)
        return app

    def test_audit_logs_requires_auth(self, app):
        client = TestClient(app)
        resp = client.get("/admin/audit-logs")
        assert resp.status_code == 403

    def test_audit_log_summary_requires_auth(self, app):
        client = TestClient(app)
        resp = client.get("/admin/audit-logs/summary")
        assert resp.status_code == 403
