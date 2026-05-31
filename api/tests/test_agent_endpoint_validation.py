import asyncio

import httpx
import pytest
from fastapi import HTTPException

from api.routes import agents as agents_route


def _run_validate(endpoint: str) -> str:
    return asyncio.run(agents_route._validate_endpoint_url(endpoint))


def test_valid_url_is_accepted_and_uses_five_second_timeout(monkeypatch):
    observed = {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            observed["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def head(self, endpoint):
            return httpx.Response(200, request=httpx.Request("HEAD", endpoint))

    monkeypatch.setattr(agents_route.httpx, "AsyncClient", MockAsyncClient)

    endpoint = "https://8.8.8.8/agent"
    assert _run_validate(endpoint) == endpoint
    assert observed["timeout"] == agents_route.ENDPOINT_TIMEOUT_SECONDS


def test_invalid_format_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        _run_validate("ftp://example.com/agent")

    assert excinfo.value.status_code == 400
    assert "http or https" in excinfo.value.detail


def test_private_ip_is_blocked_before_network_probe(monkeypatch):
    class ShouldNotBeCalled:
        def __init__(self, *args, **kwargs):  # pragma: no cover - defensive check
            raise AssertionError("HEAD probe should not run for private IP")

    monkeypatch.setattr(agents_route.httpx, "AsyncClient", ShouldNotBeCalled)

    with pytest.raises(HTTPException) as excinfo:
        _run_validate("http://127.0.0.1:9000/agent")

    assert excinfo.value.status_code == 400
    assert "private/internal IP" in excinfo.value.detail


def test_timeout_is_rejected():
    class TimeoutAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def head(self, endpoint):
            raise httpx.TimeoutException("timed out")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(agents_route.httpx, "AsyncClient", TimeoutAsyncClient)
        with pytest.raises(HTTPException) as excinfo:
            _run_validate("https://8.8.8.8/agent")

    assert excinfo.value.status_code == 400
    assert "timed out after 5s" in excinfo.value.detail


def test_create_agent_stores_validated_endpoint(monkeypatch):
    class DummyDB:
        def __init__(self):
            self.added = None

        def add(self, instance):
            self.added = instance

        def commit(self):
            return None

        def refresh(self, instance):
            instance.id = 42

    async def fake_validate(endpoint: str) -> str:
        return "https://agent.example.com/entry"

    monkeypatch.setattr(agents_route, "_validate_endpoint_url", fake_validate)

    payload = agents_route.AgentCreate(name="demo", endpoint="https://ignored.invalid")
    db = DummyDB()

    result = asyncio.run(
        agents_route.create_agent(payload, user={"id": 7, "address": "0xabc"}, db=db)
    )

    assert db.added.endpoint == "https://agent.example.com/entry"
    assert result["endpoint"] == "https://agent.example.com/entry"
