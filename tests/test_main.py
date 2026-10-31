"""Tests for request ID middleware."""

import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_request_id_generated(client):
    """Request ID is generated when not provided."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Should be a valid UUID
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36


def test_client_provided_request_id(client):
    """Client-provided X-Request-ID is accepted."""
    custom_id = "test-request-id-123"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_request_id_in_response(client):
    """X-Request-ID present in all responses."""
    response = client.get("/health")
    assert "X-Request-ID" in response.headers


def test_request_id_unique(client):
    """Each request gets a unique request ID."""
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]
