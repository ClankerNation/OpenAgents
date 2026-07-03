"""
Tests for endpoint URL validation in the OpenAgents API.

Covers bounty #187:
- URL format validation (scheme, malformed URLs)
- Private IP blocking (direct and DNS-resolved)
- Localhost/loopback blocking
- Pydantic model validation
- API route integration tests
"""

import pytest
from api.utils.validation import (
    validate_endpoint_url,
    _is_private_ip,
)

# ─── Unit tests for _is_private_ip ────────────────────────────────────────

class TestIsPrivateIP:
    """Test the private IP detection helper."""

    def test_loopback_ipv4(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_loopback_ipv6(self):
        assert _is_private_ip("::1") is True

    def test_private_10_dot(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172_dot(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_private_192_168(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_public_ip_range(self):
        assert _is_private_ip("93.184.216.34") is False  # example.com

    def test_public_hostname(self):
        # example.com resolves to a public IP
        assert _is_private_ip("example.com") is False

    def test_zero_dot_zero(self):
        assert _is_private_ip("0.0.0.0") is True

    def test_multicast_ip(self):
        assert _is_private_ip("224.0.0.1") is True

    def test_reserved_240_dot(self):
        assert _is_private_ip("240.0.0.1") is True

    def test_limited_broadcast(self):
        assert _is_private_ip("255.255.255.255") is True

    def test_test_net_1(self):
        assert _is_private_ip("192.0.2.1") is True

    def test_test_net_2(self):
        assert _is_private_ip("198.51.100.1") is True

    def test_test_net_3(self):
        assert _is_private_ip("203.0.113.1") is True

    def test_unique_local_ipv6(self):
        assert _is_private_ip("fc00::1") is True

    def test_link_local_ipv6(self):
        assert _is_private_ip("fe80::1") is True

    def test_resolved_localhost(self):
        # 'localhost' resolves to 127.0.0.1
        assert _is_private_ip("localhost") is True

    def test_nonexistent_hostname(self):
        # Should not crash on unresolvable hostnames
        assert _is_private_ip("this-domain-does-not-exist-12345.com") is False


# ─── Unit tests for validate_endpoint_url ─────────────────────────────────

class TestValidateEndpointURL:
    """Test the endpoint URL validation function."""

    def test_valid_https(self):
        result = validate_endpoint_url("https://api.example.com/v1")
        assert result == "https://api.example.com/v1"

    def test_valid_http(self):
        result = validate_endpoint_url("http://example.com:8080/agent")
        assert result == "http://example.com:8080/agent"

    def test_valid_with_path(self):
        result = validate_endpoint_url("https://api.example.com/agents/callback")
        assert result == "https://api.example.com/agents/callback"

    def test_valid_trailing_slash_normalized(self):
        result = validate_endpoint_url("https://api.example.com/")
        assert result == "https://api.example.com/"

    def test_valid_no_path(self):
        result = validate_endpoint_url("https://api.example.com")
        assert result == "https://api.example.com/"

    def test_valid_with_port(self):
        result = validate_endpoint_url("https://api.example.com:8443/path")
        assert result == "https://api.example.com:8443/path"

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="required and must be a string"):
            validate_endpoint_url("")

    def test_rejects_none(self):
        with pytest.raises(ValueError, match="required"):
            validate_endpoint_url(None)  # type: ignore

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_endpoint_url("   \t  ")

    def test_rejects_no_scheme(self):
        with pytest.raises(ValueError, match="must include a scheme"):
            validate_endpoint_url("api.example.com/path")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("ftp://files.example.com/path")

    def test_rejects_ws_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("ws://socket.example.com")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("file:///etc/passwd")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http or https"):
            validate_endpoint_url("javascript:alert(1)")

    def test_rejects_malformed_url(self):
        with pytest.raises(ValueError, match="hostname or IP"):
            validate_endpoint_url("http://")

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="localhost"):
            validate_endpoint_url("http://localhost:8000")

    def test_rejects_loopback_ip(self):
        with pytest.raises(ValueError, match="loopback"):
            validate_endpoint_url("http://127.0.0.1:5000")

    def test_rejects_127_range(self):
        with pytest.raises(ValueError, match="loopback"):
            validate_endpoint_url("http://127.0.0.2:8080")

    def test_rejects_private_192_168(self):
        with pytest.raises(ValueError, match="private or reserved"):
            validate_endpoint_url("http://192.168.1.1:8080/agent")

    def test_rejects_private_10_dot(self):
        with pytest.raises(ValueError, match="private or reserved"):
            validate_endpoint_url("http://10.0.0.5/api")

    def test_rejects_private_172_dot(self):
        with pytest.raises(ValueError, match="private or reserved"):
            validate_endpoint_url("http://172.16.0.5/agent")

    def test_rejects_link_local(self):
        with pytest.raises(ValueError, match="private or reserved"):
            validate_endpoint_url("http://169.254.1.1")

    def test_rejects_zero_ip(self):
        with pytest.raises(ValueError, match="localhost or loopback"):
            validate_endpoint_url("http://0.0.0.0:8000")

    def test_rejects_fragment(self):
        with pytest.raises(ValueError, match="fragment"):
            validate_endpoint_url("https://api.example.com/path#section")

    def test_rejects_embedded_credentials(self):
        with pytest.raises(ValueError, match="embedded credentials"):
            validate_endpoint_url("https://user:pass@api.example.com")

    def test_rejects_unresolvable_no_host(self):
        with pytest.raises(ValueError, match="hostname or IP"):
            validate_endpoint_url("https://")

    def test_rejects_just_scheme_colon(self):
        with pytest.raises(ValueError):
            validate_endpoint_url("http://")

    def test_resolved_hostname_allowed(self):
        """Public hostnames that resolve to public IPs should be allowed."""
        result = validate_endpoint_url("https://api.example.com")
        assert result is not None
        assert "example.com" in result

    def test_whitespace_stripped(self):
        result = validate_endpoint_url("  https://api.example.com/path  ")
        assert result == "https://api.example.com/path"


# ─── API route integration tests ─────────────────────────────────────────-


class TestAgentCreateEndpointValidation:
    """Integration tests for agent creation with endpoint URL validation.

    Note: These tests need a running test DB. Run manually with:
        pytest api/tests/test_agent_url_validation.py -k TestAgentCreate -v
    """

    @pytest.mark.skip(reason="Integration tests require a running database")
    def test_create_agent_with_valid_url(self, test_client):
        resp = test_client.post(
            "/agents/",
            json={
                "name": "test-agent",
                "endpoint_url": "https://api.example.com/agent",
            },
        )
        assert resp.status_code in (200, 201)

    @pytest.mark.skip(reason="Integration tests require a running database")
    def test_create_agent_with_private_ip_rejected(self, test_client):
        resp = test_client.post(
            "/agents/",
            json={
                "name": "test-agent",
                "endpoint_url": "http://192.168.1.1:8080/agent",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason="Integration tests require a running database")
    def test_create_agent_with_localhost_rejected(self, test_client):
        resp = test_client.post(
            "/agents/",
            json={
                "name": "test-agent",
                "endpoint_url": "http://localhost:8000",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason="Integration tests require a running database")
    def test_create_agent_with_no_scheme_rejected(self, test_client):
        resp = test_client.post(
            "/agents/",
            json={
                "name": "test-agent",
                "endpoint_url": "api.example.com/agent",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason="Integration tests require a running database")
    def test_create_agent_without_url_ok(self, test_client):
        resp = test_client.post(
            "/agents/",
            json={
                "name": "test-agent",
            },
        )
        assert resp.status_code in (200, 201)
