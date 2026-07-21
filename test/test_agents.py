"""Tests for agents.py - SQL injection prevention, input validation, auth on delete."""

import pytest
from unittest.mock import MagicMock, patch

mock_user = {"id": 1, "address": "0x1234567890abcdef1234567890abcdef12345678"}


class TestAgentCreate:
    """Test agent creation with input validation."""

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_valid_name(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        agent = AgentCreate(name="test-agent_123", description="A test agent")
        assert agent.name == "test-agent_123"

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_empty_name_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="", description="A test agent")

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_special_chars_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="test'; DROP TABLE agents;--", description="SQL injection attempt")

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_xss_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="<script>alert('xss')</script>", description="XSS attempt")

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_too_long_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="a" * 65, description="Too long")

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_unicode_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="\u0430\u0433\u0435\u043d\u0442", description="Unicode injection")

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_create_agent_spaces_rejected(self, mock_auth, mock_get_db):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception):
            AgentCreate(name="my agent name", description="Spaces in name")


class TestPaginationCap:
    """Test pagination limit enforcement."""

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_pagination_limit_clamped(self, mock_auth, mock_get_db):
        from api.routes.agents import MAX_PAGINATION_LIMIT
        assert MAX_PAGINATION_LIMIT == 100


class TestAuthOnDelete:
    """Test that delete requires authentication."""

    @patch("api.routes.agents.get_db", return_value=MagicMock())
    @patch("api.routes.agents.get_current_user", return_value=mock_user)
    def test_delete_requires_user_dependency(self, mock_auth, mock_get_db):
        from api.routes.agents import delete_agent
        import inspect
        sig = inspect.signature(delete_agent)
        params = list(sig.parameters.keys())
        assert "user" in params, "delete_agent must have user parameter"
        assert "db" in params, "delete_agent must have db parameter"
