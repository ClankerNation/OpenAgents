"""Tests for agent endpoint URL validation."""

import pytest
from api.routes.agents import AgentCreate, validate_endpoint_url
from pydantic import ValidationError


class TestValidateEndpointUrl:
    """Unit tests for the validate_endpoint_url function."""

    def test_none_accepted(self):
        """None endpoint should pass validation."""
        assert validate_endpoint_url(None) is None

    def test_valid_https_url(self):
        """Valid HTTPS URL should pass."""
        result = validate_endpoint_url("https://api.example.com/webhook")
        assert result == "https://api.example.com/webhook"

    def test_valid_http_url(self):
        """Valid HTTP URL should pass."""
        result = validate_endpoint_url("http://api.example.com:8080/callback")
        assert result == "http://api.example.com:8080/callback"

    def test_no_scheme(self):
        """URL without scheme should be rejected."""
        with pytest.raises(ValueError, match="scheme"):
            validate_endpoint_url("api.example.com/webhook")

    def test_ftp_scheme(self):
        """Non-http/https scheme should be rejected."""
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("ftp://files.example.com")

    def test_ws_scheme(self):
        """WebSocket scheme should be rejected."""
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("ws://socket.example.com")

    def test_malformed_url(self):
        """Completely malformed URL should be rejected."""
        with pytest.raises(ValueError, match="scheme"):
            validate_endpoint_url("not-a-url")

    def test_empty_string(self):
        """Empty string should be rejected (no scheme)."""
        with pytest.raises(ValueError, match="scheme"):
            validate_endpoint_url("")

    def test_no_hostname(self):
        """URL without hostname should be rejected."""
        with pytest.raises(ValueError, match="hostname"):
            validate_endpoint_url("https:///path")

    def test_private_ip_10_x(self):
        """Private IP 10.x.x.x should be rejected."""
        with pytest.raises(ValueError, match="private"):
            validate_endpoint_url("http://10.0.0.1/webhook")

    def test_private_ip_192_168(self):
        """Private IP 192.168.x.x should be rejected."""
        with pytest.raises(ValueError, match="private"):
            validate_endpoint_url("http://192.168.1.100/callback")

    def test_private_ip_172_16(self):
        """Private IP 172.16.x.x should be rejected."""
        with pytest.raises(ValueError, match="private"):
            validate_endpoint_url("http://172.16.0.50/test")

    def test_loopback(self):
        """Loopback IP should be rejected."""
        with pytest.raises(ValueError, match="private"):
            validate_endpoint_url("http://127.0.0.1/agent")

    def test_public_ip(self):
        """Public IP should pass validation."""
        result = validate_endpoint_url("http://8.8.8.8/agent")
        assert result == "http://8.8.8.8/agent"

    def test_localhost_hostname(self):
        """localhost hostname should resolve to loopback and be blocked."""
        with pytest.raises(ValueError, match="private|reserved"):
            validate_endpoint_url("http://localhost:5000/agent")


class TestAgentCreateUrlValidation:
    """Tests for AgentCreate Pydantic model endpoint validation."""

    def test_valid_endpoint_in_model(self):
        """AgentCreate should accept valid endpoint."""
        agent = AgentCreate(
            name="test-agent",
            endpoint="https://api.example.com/webhook",
        )
        assert agent.endpoint == "https://api.example.com/webhook"

    def test_no_endpoint(self):
        """AgentCreate should work without endpoint."""
        agent = AgentCreate(name="test-agent")
        assert agent.endpoint is None

    def test_private_ip_rejected_in_model(self):
        """AgentCreate should reject private IP endpoints."""
        with pytest.raises(ValidationError, match="private|reserved"):
            AgentCreate(
                name="test-agent",
                endpoint="http://192.168.1.1/webhook",
            )

    def test_no_scheme_rejected_in_model(self):
        """AgentCreate should reject URL without scheme."""
        with pytest.raises(ValidationError, match="scheme"):
            AgentCreate(
                name="test-agent",
                endpoint="api.example.com/webhook",
            )

    def test_bad_scheme_rejected_in_model(self):
        """AgentCreate should reject non-http/https scheme."""
        with pytest.raises(ValidationError, match="scheme"):
            AgentCreate(
                name="test-agent",
                endpoint="ftp://files.example.com",
            )
