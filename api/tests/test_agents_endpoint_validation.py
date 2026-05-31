import asyncio
import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import agents


def test_validate_endpoint_valid_url(monkeypatch):
    seen = {}

    async def fake_verify(url: str) -> None:
        seen["url"] = url

    monkeypatch.setattr(agents, "_verify_endpoint_reachable", fake_verify)

    validated = asyncio.run(agents._validate_endpoint("https://example.com/agent"))
    assert validated == "https://example.com/agent"
    assert seen["url"] == validated


def test_validate_endpoint_invalid_format(monkeypatch):
    async def fail_if_called(_: str) -> None:
        raise AssertionError("reachability check should not run for invalid URL format")

    monkeypatch.setattr(agents, "_verify_endpoint_reachable", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agents._validate_endpoint("not-a-url"))

    assert exc.value.status_code == 400
    assert "Invalid endpoint URL format" in exc.value.detail


def test_validate_endpoint_blocks_private_ip(monkeypatch):
    async def fail_if_called(_: str) -> None:
        raise AssertionError("reachability check should not run for private IP URL")

    monkeypatch.setattr(agents, "_verify_endpoint_reachable", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agents._validate_endpoint("http://127.0.0.1:8080/agent"))

    assert exc.value.status_code == 400
    assert "private or internal IP" in exc.value.detail


def test_verify_endpoint_reachable_timeout(monkeypatch):
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def head(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(agents.httpx, "AsyncClient", TimeoutClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agents._verify_endpoint_reachable("https://example.com/agent"))

    assert exc.value.status_code == 400
    assert "timed out after 5 seconds" in exc.value.detail
