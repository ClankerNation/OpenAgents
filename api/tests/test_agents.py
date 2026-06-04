# Agent: MONAI Autonomous (szamaniai)
# Timestamp: 2026-06-04T21:30:00Z
# Startup: python -m pytest api/tests/test_agents.py -v
# Env: Linux x86_64, Python 3.12, /app

"""Tests for agent endpoint URL validation."""

import pytest
from api.routes.agents import validate_agent_endpoint


def test_valid_https_url():
    """Valid HTTPS URL should pass validation."""
    result = validate_agent_endpoint("https://api.example.com/agent")
    assert result == "https://api.example.com/agent"


def test_valid_http_url():
    """Valid HTTP URL should pass validation."""
    result = validate_agent_endpoint("http://example.com:8080/agent")
    assert result == "http://example.com:8080/agent"


def test_invalid_scheme():
    """Non-http/https schemes should be rejected."""
    with pytest.raises(ValueError, match="http or https"):
        validate_agent_endpoint("ftp://example.com/agent")


def test_invalid_scheme_ws():
    """WebSocket schemes should be rejected."""
    with pytest.raises(ValueError, match="http or https"):
        validate_agent_endpoint("ws://example.com/agent")


def test_empty_url():
    """Empty URL should be rejected."""
    with pytest.raises(ValueError):
        validate_agent_endpoint("")


def test_no_hostname():
    """URL without hostname should be rejected."""
    with pytest.raises(ValueError, match="hostname"):
        validate_agent_endpoint("http:///path")


def test_private_ip():
    """Private IP 10.x.x.x should be rejected."""
    with pytest.raises(ValueError, match="Private IP"):
        validate_agent_endpoint("http://10.0.0.1:8000/agent")


def test_private_ip_192():
    """Private IP 192.168.x.x should be rejected."""
    with pytest.raises(ValueError, match="Private IP"):
        validate_agent_endpoint("http://192.168.1.1/agent")


def test_loopback_ip():
    """Loopback IP 127.x.x.x should be rejected."""
    with pytest.raises(ValueError, match="Loopback"):
        validate_agent_endpoint("http://127.0.0.1:8000/agent")


def test_link_local_ip():
    """Link-local IP 169.254.x.x should be rejected."""
    with pytest.raises(ValueError, match="Link-local"):
        validate_agent_endpoint("http://169.254.1.1/agent")


def test_multicast_ip():
    """Multicast IP 224.x.x.x should be rejected."""
    with pytest.raises(ValueError, match="Multicast"):
        validate_agent_endpoint("http://224.0.0.1/agent")


def test_ipv6_loopback():
    """IPv6 loopback ::1 should be rejected."""
    with pytest.raises(ValueError, match="Loopback|Private"):
        validate_agent_endpoint("http://[::1]:8000/agent")


def test_url_with_path():
    """URL with path should pass if host is public."""
    result = validate_agent_endpoint("https://valid.example.com/api/v1/agent")
    assert "valid.example.com" in result


def test_url_with_query():
    """URL with query params should pass."""
    result = validate_agent_endpoint("https://valid.example.com/agent?version=2")
    assert result is not None


def test_unresolvable_hostname():
    """Unresolvable hostname should be rejected."""
    with pytest.raises(ValueError, match="Cannot resolve|not reachable"):
        validate_agent_endpoint("http://this-domain-does-not-exist-12345.com/agent")
