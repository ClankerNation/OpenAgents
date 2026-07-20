"""Tests for RequestIDMiddleware."""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_request_id_header_present():
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_request_id_unique():
    resp1 = client.get("/health")
    resp2 = client.get("/health")
    assert resp1.headers["X-Request-ID"] != resp2.headers["X-Request-ID"]
