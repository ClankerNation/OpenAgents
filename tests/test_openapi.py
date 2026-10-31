"""Tests for OpenAPI security schemes."""

import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_openapi_has_security_schemes(client):
    """OpenAPI spec includes security schemes."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "securitySchemes" in spec["components"]
    assert "BearerAuth" in spec["components"]["securitySchemes"]
    assert "ApiKeyAuth" in spec["components"]["securitySchemes"]


def test_bearer_auth_scheme(client):
    """BearerAuth scheme is http/bearer."""
    response = client.get("/openapi.json")
    spec = response.json()
    bearer = spec["components"]["securitySchemes"]["BearerAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"
    assert bearer["bearerFormat"] == "JWT"


def test_api_key_auth_scheme(client):
    """ApiKeyAuth scheme is apiKey in header."""
    response = client.get("/openapi.json")
    spec = response.json()
    api_key = spec["components"]["securitySchemes"]["ApiKeyAuth"]
    assert api_key["type"] == "apiKey"
    assert api_key["in"] == "header"
    assert api_key["name"] == "X-API-Key"


def test_endpoints_have_security(client):
    """Endpoints include security requirements."""
    response = client.get("/openapi.json")
    spec = response.json()
    # Check that at least one endpoint has security
    for path, methods in spec["paths"].items():
        for method, details in methods.items():
            if method in ("get", "post", "put", "delete", "patch"):
                assert "security" in details
                break
        break


def test_401_response_documented(client):
    """401 response is documented in OpenAPI spec."""
    response = client.get("/openapi.json")
    spec = response.json()
    # Check that endpoints have 401 response
    found_401 = False
    for path, methods in spec["paths"].items():
        for method, details in methods.items():
            if method in ("get", "post", "put", "delete", "patch"):
                if "401" in details.get("responses", {}):
                    found_401 = True
                    break
        if found_401:
            break
    assert found_401
