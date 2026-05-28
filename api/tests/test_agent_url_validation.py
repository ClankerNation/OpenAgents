"""Tests for agent endpoint URL validation."""

import pytest
import sys
import os
import httpx
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.routes.agents import (
    _validate_endpoint_url,
    _is_private_ip,
    _check_reachability,
)
from fastapi import HTTPException


class TestIsPrivateIp:
    def test_private_10_network(self):
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True

    def test_private_172_network(self):
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True

    def test_private_192_network(self):
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("192.168.0.0") is True

    def test_localhost(self):
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.255.255.255") is True

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False

    def test_hostname_not_ip(self):
        assert _is_private_ip("example.com") is False


class TestValidateEndpointUrl:
    def test_valid_http_url(self):
        result = _validate_endpoint_url("http://example.com/api")
        assert result == "http://example.com/api"

    def test_valid_https_url(self):
        result = _validate_endpoint_url("https://example.com/api")
        assert result == "https://example.com/api"

    def test_ftp_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("ftp://example.com")
        assert exc_info.value.status_code == 422
        assert "http or https" in exc_info.value.detail

    def test_no_scheme_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("example.com")
        assert exc_info.value.status_code == 422

    def test_private_ip_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("http://192.168.1.1/api")
        assert exc_info.value.status_code == 422
        assert "private" in exc_info.value.detail.lower()

    def test_localhost_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("http://127.0.0.1:8080/api")
        assert exc_info.value.status_code == 422

    def test_10_network_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("http://10.0.0.1/api")
        assert exc_info.value.status_code == 422

    def test_empty_hostname_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_endpoint_url("http://")
        assert exc_info.value.status_code == 422


class TestCheckReachability:
    @pytest.mark.asyncio
    async def test_reachable_url(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.head", return_value=mock_response):
            await _check_reachability("https://example.com")

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        import httpx

        with patch("httpx.AsyncClient.head", side_effect=httpx.TimeoutException("timeout")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_reachability("https://slow.example.com")
            assert exc_info.value.status_code == 422
            assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_connection_error_raises(self):
        with patch("httpx.AsyncClient.head", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_reachability("https://down.example.com")
            assert exc_info.value.status_code == 422
            assert "connection" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_server_error_raises(self):
        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient.head", return_value=mock_response):
            with pytest.raises(HTTPException) as exc_info:
                await _check_reachability("https://broken.example.com")
            assert exc_info.value.status_code == 422
            assert "server error" in exc_info.value.detail.lower()
