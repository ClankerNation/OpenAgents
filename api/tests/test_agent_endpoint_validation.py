import asyncio
import ipaddress
import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import agents


class _DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _SuccessClient:
    def __init__(self, timeout=None, follow_redirects=False):
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def head(self, url: str):
        return _DummyResponse(200)


class _TimeoutClient(_SuccessClient):
    async def head(self, url: str):
        raise httpx.TimeoutException("timed out")


def test_validate_agent_endpoint_accepts_valid_http_url(monkeypatch):
    monkeypatch.setattr(
        agents,
        "_resolve_hostname_addresses",
        lambda hostname: [ipaddress.ip_address("93.184.216.34")],
    )
    monkeypatch.setattr(agents.httpx, "AsyncClient", _SuccessClient)

    validated = asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert validated == "https://example.com/agent"


def test_validate_agent_endpoint_rejects_invalid_url_format():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("not-a-url"))

    assert exc_info.value.status_code == 422
    assert "valid http/https URL" in exc_info.value.detail


def test_validate_agent_endpoint_rejects_private_ip():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("http://127.0.0.1/agent"))

    assert exc_info.value.status_code == 422
    assert "private/internal IP" in exc_info.value.detail


def test_validate_agent_endpoint_rejects_timeout(monkeypatch):
    monkeypatch.setattr(
        agents,
        "_resolve_hostname_addresses",
        lambda hostname: [ipaddress.ip_address("93.184.216.34")],
    )
    monkeypatch.setattr(agents.httpx, "AsyncClient", _TimeoutClient)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert exc_info.value.status_code == 422
    assert "timed out" in exc_info.value.detail
