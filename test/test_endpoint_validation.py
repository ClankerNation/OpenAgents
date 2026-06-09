"""
Tests for agent endpoint URL validation.

Covers:
- Valid URL format (http/https)
- Invalid URL format rejected
- Private IP addresses blocked (SSRF protection)
- Timeout handling
- Reachability verification
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock
from urllib.parse import urlparse
import ipaddress

from api.routes.agents import (
    _is_private_ip,
    _validate_endpoint_url,
    PRIVATE_PREFIXES,
)


class TestPrivateIPDetection:
    """Tests for _is_private_ip SSRF protection logic."""

    def test_private_ipv4_10_dot(self):
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True

    def test_private_ipv4_192_168(self):
        assert _is_private_ip("192.168.0.1") is True
        assert _is_private_ip("192.168.255.255") is True

    def test_private_ipv4_172_16(self):
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True

    def test_loopback_ipv4(self):
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.0.0.0") is True

    def test_link_local_ipv4(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_loopback_ipv6(self):
        assert _is_private_ip("::1") is True

    def test_public_ipv4(self):
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False
        assert _is_private_ip("93.184.216.34") is False

    def test_public_hostname(self):
        """Hostnames that resolve to public IPs should return False."""
        # example.com resolves to public IPs
        assert _is_private_ip("example.com") is False


class TestValidateEndpointURL:
    """Tests for _validate_endpoint_url with mocked HTTP."""

    @patch("api.routes.agents.httpx.AsyncClient")
    async def test_valid_public_url(self, mock_client):
        mock_instance = AsyncMock()
        mock_instance.head.return_value.status_code = 200
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await _validate_endpoint_url("https://example.com/agent")
        assert result == "https://example.com/agent"

    @patch("api.routes.agents.httpx.AsyncClient")
    async def test_valid_http_url(self, mock_client):
        mock_instance = AsyncMock()
        mock_instance.head.return_value.status_code = 200
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await _validate_endpoint_url("http://example.com/agent")
        assert result == "http://example.com/agent"

    async def test_invalid_scheme_ftp(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("ftp://example.com/agent")
        assert "http" in str(excinfo.value).lower() or "https" in str(excinfo.value).lower()

    async def test_invalid_scheme_random(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("gopher://example.com/agent")
        assert "http" in str(excinfo.value).lower() or "https" in str(excinfo.value).lower()

    async def test_no_hostname(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("http:///path")
        assert "hostname" in str(excinfo.value).lower()

    async def test_private_ip_10_dot_rejected(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("http://10.0.0.1/agent")
        assert "private" in str(excinfo.value).lower() or "internal" in str(excinfo.value).lower()

    async def test_private_ip_192_168_rejected(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("http://192.168.1.1/agent")
        assert "private" in str(excinfo.value).lower() or "internal" in str(excinfo.value).lower()

    async def test_loopback_rejected(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("http://127.0.0.1/agent")
        assert "private" in str(excinfo.value).lower() or "internal" in str(excinfo.value).lower()

    async def test_ipv6_loopback_rejected(self):
        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("http://[::1]/agent")
        assert "private" in str(excinfo.value).lower() or "internal" in str(excinfo.value).lower()

    @patch("api.routes.agents.httpx.AsyncClient")
    async def test_timeout_returns_error(self, mock_client):
        mock_instance = AsyncMock()
        mock_instance.head.side_effect = httpx.TimeoutException("timeout")
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("https://example.com/agent")
        assert "timeout" in str(excinfo.value).lower()

    @patch("api.routes.agents.httpx.AsyncClient")
    async def test_server_error_rejected(self, mock_client):
        mock_instance = AsyncMock()
        mock_instance.head.return_value.status_code = 502
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("https://example.com/agent")
        assert "unreachable" in str(excinfo.value).lower() or "502" in str(excinfo.value)

    @patch("api.routes.agents.httpx.AsyncClient")
    async def test_unresolvable_hostname(self, mock_client):
        mock_instance = AsyncMock()
        mock_instance.head.side_effect = httpx.RequestError("Name or service not known")
        mock_client.return_value.__aenter__.return_value = mock_instance

        with pytest.raises(Exception) as excinfo:
            await _validate_endpoint_url("https://nonexistent-domain-12345.com/agent")
        assert "unreachable" in str(excinfo.value).lower()


class TestPydanticValidation:
    """Tests for Pydantic model-level validation."""

    def test_agent_create_valid(self):
        from api.routes.agents import AgentCreate
        agent = AgentCreate(name="test-agent", endpoint="https://example.com/agent")
        assert agent.name == "test-agent"
        assert agent.endpoint == "https://example.com/agent"

    def test_agent_create_empty_name(self):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception) as excinfo:
            AgentCreate(name="", endpoint="https://example.com/agent")
        assert "empty" in str(excinfo.value).lower()

    def test_agent_create_invalid_scheme(self):
        from api.routes.agents import AgentCreate
        with pytest.raises(Exception) as excinfo:
            AgentCreate(name="test", endpoint="ftp://example.com/agent")
        assert "http" in str(excinfo.value).lower() or "https" in str(excinfo.value).lower()

    def test_agent_update_valid(self):
        from api.routes.agents import AgentUpdate
        update = AgentUpdate(endpoint="https://new-endpoint.com/agent")
        assert update.endpoint == "https://new-endpoint.com/agent"

    def test_agent_update_invalid_endpoint(self):
        from api.routes.agents import AgentUpdate
        with pytest.raises(Exception) as excinfo:
            AgentUpdate(endpoint="invalid-url")
        assert "http" in str(excinfo.value).lower() or "https" in str(excinfo.value).lower()
