import pytest
from fastapi.testclient import TestClient
import uuid
from api.main import app

client = TestClient(app)

def test_request_id_header():
    response = client.get("/health")
    assert "X-Request-ID" in response.headers

def test_client_provided_id_passthrough():
    rid = str(uuid.uuid4())
    response = client.get("/health", headers={"X-Request-ID": rid})
    assert response.headers["X-Request-ID"] == rid

def test_unique_ids():
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]

def test_valid_uuid():
    response = client.get("/health")
    uuid.UUID(response.headers["X-Request-ID"])
