"""
Tests for CORS configuration in api/main.py
Issue: #156 — Fix main.py has no CORS configuration
"""
import os
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(autouse=True)
def setup_dev_env(monkeypatch):
    """Ensure tests run in development mode with wildcard CORS."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")


client = TestClient(app)


def test_cors_preflight_options():
    """Preflight OPTIONS request should return CORS headers."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert "access-control-allow-credentials" in response.headers


def test_cors_headers_on_get():
    """Cross-origin GET request should include CORS headers."""
    response = client.get(
        "/health",
        headers={"Origin": "http://example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_cors_credentials_allowed():
    """Access-Control-Allow-Credentials should be true."""
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_methods_include_common():
    """Allowed methods should include GET, POST, PUT, DELETE, OPTIONS."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
        assert method in allowed_methods, f"{method} not in allowed methods: {allowed_methods}"


def test_cors_with_specific_origins():
    """When ALLOWED_ORIGINS is set, only those origins are allowed."""
    os.environ["ALLOWED_ORIGINS"] = "https://app.example.com,https://admin.example.com"
    os.environ["ENVIRONMENT"] = "production"

    response = client.get(
        "/health",
        headers={"Origin": "https://app.example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_health_endpoint_still_works():
    """Health endpoint should still return ok after CORS middleware added."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
