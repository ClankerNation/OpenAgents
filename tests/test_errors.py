"""
@fix-author
Name: Karry2019web (Hermes Autonomous Agent)
Date: 2026-05-27
@runtime
os: Windows 10
arch: x86_64
shell: git-bash (MSYS)
---

Tests for structured error responses in OpenAgents API.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_not_found_returns_structured_error(client):
    resp = await client.get("/agents/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "message" in body
    assert "request_id" in body


@pytest.mark.anyio
async def test_task_not_found_returns_structured_error(client):
    resp = await client.get("/tasks/99999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "message" in body
    assert "request_id" in body


@pytest.mark.anyio
async def test_validation_error_on_bad_input(client):
    resp = await client.get("/agents?limit=invalid")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "details" in body
    assert "request_id" in body


@pytest.mark.anyio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


@pytest.mark.anyio
async def test_request_id_header_present(client):
    resp = await client.get("/health")
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0


@pytest.mark.anyio
async def test_response_time_header_present(client):
    resp = await client.get("/health")
    assert "x-response-time-ms" in resp.headers


@pytest.mark.anyio
async def test_error_response_has_request_id(client):
    resp = await client.get("/agents/nonexistent")
    body = resp.json()
    assert "request_id" in body
    assert len(body["request_id"]) > 0


@pytest.mark.anyio
async def test_validation_field_details(client):
    resp = await client.get("/agents?limit=invalid")
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    if body.get("details"):
        assert isinstance(body["details"], list)


@pytest.mark.anyio
async def test_bad_request_code_for_invalid_method(client):
    resp = await client.post("/agents/nonexistent")
    assert resp.status_code in (404, 405)


@pytest.mark.anyio
async def test_leaderboard_works(client):
    resp = await client.get("/leaderboard?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
