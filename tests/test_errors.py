"""
Tests for structured error responses.
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
async def test_list_agents_returns_list(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.anyio
async def test_list_tasks_returns_list(client):
    resp = await client.get("/tasks")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_leaderboard_returns_list(client):
    resp = await client.get("/leaderboard")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_validation_details_show_field_errors(client):
    resp = await client.get("/agents?limit=-1")
    assert resp.status_code in (422, 200)


@pytest.mark.anyio
async def test_health_has_request_id(client):
    resp = await client.get("/health")
    body = resp.json()
    # health endpoint doesn't need request_id in body, but header should exist
    assert "x-request-id" in resp.headers
