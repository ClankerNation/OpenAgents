import os

import anyio
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import get_db
from api.middleware.auth import get_current_user
from api.routes import agents


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeHeadClient:
    def __init__(self, response=None, error=None, **_kwargs):
        self.response = response or FakeResponse()
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def head(self, _url):
        if self.error:
            raise self.error
        return self.response


class FakeDb:
    def add(self, agent):
        self.agent = agent
        agent.id = 42

    def commit(self):
        pass

    def refresh(self, _agent):
        pass


def make_app(db):
    app = FastAPI()
    app.include_router(agents.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 7, "address": "0xabc"}
    app.dependency_overrides[get_db] = lambda: db
    return app


def test_create_agent_stores_validated_endpoint(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(agents, "_is_private_host", lambda _host: False)
    monkeypatch.setattr(agents.httpx, "AsyncClient", FakeHeadClient)

    client = TestClient(make_app(db))
    response = client.post(
        "/agents/",
        json={
            "name": "worker",
            "endpoint": "https://agent.example.com/callback",
            "model_type": "gpt-4",
        },
    )

    assert response.status_code == 200
    assert response.json()["endpoint"] == "https://agent.example.com/callback"
    assert db.agent.endpoint == "https://agent.example.com/callback"


def test_rejects_invalid_endpoint_format():
    with pytest.raises(HTTPException) as exc:
        anyio.run(agents.validate_endpoint_url, "not-a-url")

    assert exc.value.status_code == 400
    assert "valid http or https URL" in exc.value.detail


def test_rejects_private_ip_endpoint():
    with pytest.raises(HTTPException) as exc:
        anyio.run(agents.validate_endpoint_url, "http://127.0.0.1:8080/agent")

    assert exc.value.status_code == 400
    assert "private address" in exc.value.detail


def test_rejects_endpoint_timeout(monkeypatch):
    monkeypatch.setattr(agents, "_is_private_host", lambda _host: False)
    monkeypatch.setattr(
        agents.httpx,
        "AsyncClient",
        lambda **kwargs: FakeHeadClient(
            error=httpx.TimeoutException("timed out"),
            **kwargs,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        anyio.run(agents.validate_endpoint_url, "https://agent.example.com/callback")

    assert exc.value.status_code == 400
    assert "timed out" in exc.value.detail


def test_rejects_unreachable_endpoint(monkeypatch):
    monkeypatch.setattr(agents, "_is_private_host", lambda _host: False)
    monkeypatch.setattr(
        agents.httpx,
        "AsyncClient",
        lambda **kwargs: FakeHeadClient(response=FakeResponse(503), **kwargs),
    )

    with pytest.raises(HTTPException) as exc:
        anyio.run(agents.validate_endpoint_url, "https://agent.example.com/callback")

    assert exc.value.status_code == 400
    assert "not reachable" in exc.value.detail
