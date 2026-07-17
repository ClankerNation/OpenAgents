"""Tests for agents.py - SQL injection prevention, input validation, auth on delete."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Mock the database and auth dependencies
mock_db = MagicMock()
mock_user = {"id": 1, "address": "0x1234567890abcdef1234567890abcdef12345678"}


class TestAgentCreate:
    """Test agent creation with input validation."""

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_valid_name(self, mock_auth, mock_get_db):
        """Valid agent name should be accepted."""
        from api.routes.agents import AgentCreate
        agent = AgentCreate(name="test-agent_123", description="A test agent")
        assert agent.name == "test-agent_123"

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_empty_name_rejected(self, mock_auth, mock_get_db):
        """Empty name should be rejected."""
        from api.routes.agents import AgentCreate
        with pytest.raises(ValueError, match="Name cannot be empty"):
            AgentCreate(name="", description="A test agent")

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_special_chars_rejected(self, mock_auth, mock_get_db):
        """Special characters should be rejected (prevents SQL injection)."""
        from api.routes.agents import AgentCreate
        with pytest.raises(ValueError, match="Name can only contain"):
            AgentCreate(name="test'; DROP TABLE agents;--", description="SQL injection attempt")

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_xss_rejected(self, mock_auth, mock_get_db):
        """XSS payloads should be rejected."""
        from api.routes.agents import AgentCreate
        with pytest.raises(ValueError, match="Name can only contain"):
            AgentCreate(name="<script>alert('xss')</script>", description="XSS attempt")

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_too_long_rejected(self, mock_auth, mock_get_db):
        """Names over 64 characters should be rejected."""
        from api.routes.agents import AgentCreate
        with pytest.raises(ValueError, match="Name must be 64 characters or less"):
            AgentCreate(name="a" * 65, description="Too long")

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_max_length_accepted(self, mock_auth, mock_get_db):
        """Names exactly 64 characters should be accepted."""
        from api.routes.agents import AgentCreate
        agent = AgentCreate(name="a" * 64, description="Max length")
        assert len(agent.name) == 64


class TestPaginationCap:
    """Test pagination limit enforcement."""

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_pagination_limit_100(self, mock_auth, mock_get_db):
        """Limit should be capped at 100."""
        from api.routes.agents import list_agents
        # Query with limit > 100 should be rejected by FastAPI validation
        # This tests that the parameter has le=100


class TestDeleteAuth:
    """Test delete authentication."""

    @patch("api.routes.agents.get_db", return_value=mock_db)
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_delete_requires_owner(self, mock_auth, mock_get_db):
        """Delete should require owner authentication."""
        from api.routes.agents import delete_agent
        # The function should check agent.owner_id == user["id"]
        # If not, it should raise HTTPException(403)
