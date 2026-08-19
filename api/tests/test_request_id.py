"""Tests for Request ID middleware (Issue #178)."""
import pytest
from fastapi.testclient import TestClient
import os

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app

client = TestClient(app)

def test_response_has_request_id_header():
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    request_id = response.headers["x-request-id"]
    assert len(request_id) > 0

def test_client_provided_id_preserved():
    custom_id = "custom-trace-id-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id

def test_ids_unique_per_request():
    response1 = client.get("/health")
    response2 = client.get("/health")
    
    id1 = response1.headers["x-request-id"]
    id2 = response2.headers["x-request-id"]
    
    assert id1 != id2
