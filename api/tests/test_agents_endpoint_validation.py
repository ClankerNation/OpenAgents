import asyncio
import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import agents
from api.routes.agents import AgentCreate, create_agent, validate_agent_endpoint


class _HeadOkClient:
    def __init__(self, *args, **kwargs):
        self.called_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def head(self, url):
        self.called_url = url
        return object()


class _HeadTimeoutClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def head(self, url):
        raise httpx.ReadTimeout("timed out")


def _public_dns_result(*args, **kwargs):
    return [(0, 0, 0, "", ("93.184.216.34", 0))]


def test_validate_agent_endpoint_accepts_valid_url(monkeypatch):
    monkeypatch.setattr(agents.socket, "getaddrinfo", _public_dns_result)
    monkeypatch.setattr(agents.httpx, "AsyncClient", _HeadOkClient)

    result = asyncio.run(validate_agent_endpoint("https://example.com/agent"))

    assert result == "https://example.com/agent"


def test_validate_agent_endpoint_rejects_invalid_format():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_agent_endpoint("example.com/no-scheme"))

    assert exc.value.status_code == 400
    assert "Invalid endpoint URL format" in exc.value.detail


def test_validate_agent_endpoint_rejects_private_ip():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_agent_endpoint("http://127.0.0.1:8000/agent"))

    assert exc.value.status_code == 400
    assert "private or internal IP" in exc.value.detail


def test_validate_agent_endpoint_rejects_head_timeout(monkeypatch):
    monkeypatch.setattr(agents.socket, "getaddrinfo", _public_dns_result)
    monkeypatch.setattr(agents.httpx, "AsyncClient", _HeadTimeoutClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_agent_endpoint("https://example.com/agent"))

    assert exc.value.status_code == 400
    assert "timed out" in exc.value.detail


class _FakeDB:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj
        obj.id = 1

    def commit(self):
        pass

    def refresh(self, obj):
        pass


def test_create_agent_stores_validated_endpoint(monkeypatch):
    async def _fake_validate(endpoint):
        return "https://validated.example/agent"

    monkeypatch.setattr(agents, "validate_agent_endpoint", _fake_validate)
    db = _FakeDB()
    payload = AgentCreate(
        name="worker-1",
        endpoint="https://example.com/raw",
        config={"temperature": 0.1},
    )

    response = asyncio.run(create_agent(payload, user={"id": 11, "address": "0xabc"}, db=db))

    assert response["id"] == 1
    assert db.added.config["endpoint"] == "https://validated.example/agent"
    assert db.added.config["temperature"] == 0.1
