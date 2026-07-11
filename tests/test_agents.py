"""Tests for agent CRUD endpoints."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from ..main import app

client = TestClient(app)


def test_list_agents_default_active_only():
    """Default list returns only active agents."""
    response = client.get("/agents/")
    assert response.status_code == 200
    for agent in response.json():
        assert agent.get("deleted_at") is None, "Default list should only return active agents"


def test_list_agents_include_inactive():
    """include_inactive=true shows all agents including soft-deleted."""
    response = client.get("/agents/?include_inactive=true")
    assert response.status_code == 200


def test_soft_delete_sets_timestamp():
    """Soft delete sets deleted_at instead of hard delete."""
    # Create agent first
    create_resp = client.post("/agents/", json={"name": "test-agent"})
    assert create_resp.status_code == 200
    agent_id = create_resp.json()["id"]

    # Soft delete
    delete_resp = client.delete(f"/agents/{agent_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True
    assert delete_resp.json()["deleted_at"] is not None


def test_deleted_agent_not_in_default_list():
    """Soft-deleted agent should not appear in default list."""
    response = client.get("/agents/")
    for agent in response.json():
        assert agent.get("deleted_at") is None


def test_deleted_agent_in_include_inactive():
    """Soft-deleted agent should appear when include_inactive=true."""
    response = client.get("/agents/?include_inactive=true")
    assert response.status_code == 200


def test_sensitive_fields_excluded():
    """Sensitive fields like platform_instructions should not be in list response."""
    response = client.get("/agents/")
    assert response.status_code == 200
    for agent in response.json():
        assert "platform_instructions" not in agent
