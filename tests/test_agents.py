"""Tests for agent endpoint URL validation."""

import pytest
from pydantic import ValidationError

from api.routes.agents import _validate_url, _is_private_ip


def test_valid_http_url():
    """Valid HTTP URL passes validation."""
    result = _validate_url("http://example.com/api")
    assert result == "http://example.com/api"


def test_valid_https_url():
    """Valid HTTPS URL passes validation."""
    result = _validate_url("https://example.com/api")
    assert result == "https://example.com/api"


def test_empty_url_rejected():
    """Empty URL is rejected."""
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_url("")


def test_invalid_scheme_rejected():
    """Non-http/https scheme is rejected."""
    with pytest.raises(ValueError, match="http or https"):
        _validate_url("ftp://example.com")


def test_no_host_rejected():
    """URL without host is rejected."""
    with pytest.raises(ValueError, match="valid host"):
        _validate_url("http://")


def test_private_ip_10_rejected():
    """Private IP 10.x is rejected."""
    assert _is_private_ip("10.0.0.1") is True


def test_private_ip_192_rejected():
    """Private IP 192.168.x is rejected."""
    assert _is_private_ip("192.168.1.1") is True


def test_private_ip_127_rejected():
    """Loopback IP 127.x is rejected."""
    assert _is_private_ip("127.0.0.1") is True


def test_public_ip_allowed():
    """Public IP is allowed."""
    assert _is_private_ip("8.8.8.8") is False


def test_private_ip_in_url_rejected():
    """URL with private IP is rejected."""
    with pytest.raises(ValueError, match="Private/internal"):
        _validate_url("http://192.168.1.1/api")


def test_localhost_rejected():
    """Localhost URL is rejected."""
    with pytest.raises(ValueError, match="Private/internal"):
        _validate_url("http://127.0.0.1/api")
