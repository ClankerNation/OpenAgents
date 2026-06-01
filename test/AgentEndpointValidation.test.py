"""Tests for agent endpoint URL validation."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


# Test the validation functions directly
def test_url_pattern_valid():
    from api.routes.agents import URL_PATTERN
    assert URL_PATTERN.match("https://agent.example.com")
    assert URL_PATTERN.match("http://api.agent.io/v1")
    assert URL_PATTERN.match("https://localhost:8080")
    assert URL_PATTERN.match("http://192.168.1.1:3000")


def test_url_pattern_invalid():
    from api.routes.agents import URL_PATTERN
    assert not URL_PATTERN.match("not-a-url")
    assert not URL_PATTERN.match("ftp://invalid.com")
    assert not URL_PATTERN.match("")
    assert not URL_PATTERN.match("just-text")


def test_is_private_ip():
    from api.routes.agents import _is_private_ip
    assert _is_private_ip("127.0.0.1")
    assert _is_private_ip("10.0.0.5")
    assert _is_private_ip("192.168.1.1")
    assert _is_private_ip("172.16.0.1")
    assert _is_private_ip("::1")
    assert not _is_private_ip("8.8.8.8")
    assert not _is_private_ip("1.1.1.1")


@patch("api.routes.agents.httpx.head")
def test_validate_endpoint_reachable(mock_head):
    from api.routes.agents import validate_endpoint

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_head.return_value = mock_response

    result = validate_endpoint("https://agent.example.com")
    assert result == "https://agent.example.com"


@patch("api.routes.agents.httpx.head")
def test_validate_endpoint_private_ip_rejected(mock_head):
    from api.routes.agents import validate_endpoint
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        validate_endpoint("http://10.0.0.5:8080")
    assert "private" in str(exc.value.detail).lower()


def test_validate_endpoint_invalid_format():
    from api.routes.agents import validate_endpoint
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        validate_endpoint("not-a-valid-url")
    assert "invalid" in str(exc.value.detail).lower()


@patch("api.routes.agents.httpx.head")
def test_validate_endpoint_timeout(mock_head):
    from api.routes.agents import validate_endpoint
    from fastapi import HTTPException
    import httpx

    mock_head.side_effect = httpx.TimeoutException("timeout")

    with pytest.raises(HTTPException) as exc:
        validate_endpoint("https://slow.example.com")
    assert "timed out" in str(exc.value.detail).lower()
