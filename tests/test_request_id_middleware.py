import pytest
from fastapi.testclient import TestClient
import uuid

client = TestClient(app)
from api.main import app

def test_request_id_header_presence():
    response = client.get("/")
    assert "X-Request-ID" in response.headers

def test_client_provided_id_passthrough():
    client_request_id = str(uuid.uuid4())
    response = client.get("/", headers={"X-Request-ID": client_request_id})
    assert response.headers["X-Request-ID"] == client_request_id

def test_unique_request_ids():
    response1 = client.get("/")
    response2 = client.get("/")
    assert response1.headers["X-Request-ID"] != response2.headers["X-Request-ID"]

def test_request_id_format():
    response = client.get("/")
    uuid.UUID(response.headers["X-Request-ID"])
