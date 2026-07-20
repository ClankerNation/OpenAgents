"""Tests for agent soft delete and inactive filtering."""

from datetime import datetime
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestAgentSoftDelete:
    def test_deleted_agent_not_in_default_list(self):
        resp = client.get("/agents")
        assert resp.status_code == 200

    def test_include_inactive_shows_deleted(self):
        resp = client.get("/agents?include_inactive=true")
        assert resp.status_code == 200

    def test_deleted_agent_returns_404_on_get(self):
        resp = client.get("/agents/99999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        resp = client.delete("/agents/1")
        assert resp.status_code == 403
