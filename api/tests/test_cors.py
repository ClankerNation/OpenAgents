"""Tests for CORS middleware configuration."""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_cors_preflight():
    """Preflight OPTIONS request should return CORS headers."""
    response = client.options(
        "/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_cors_cross_origin_get():
    """Cross-origin GET request should return CORS headers."""
    response = client.get(
        "/health",
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_cors_credentials_allowed():
    """CORS responses should allow credentials."""
    response = client.get(
        "/health",
        headers={"Origin": "https://example.com"},
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_allowed_methods():
    """CORS preflight should include standard HTTP methods."""
    response = client.options(
        "/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    allow_methods = response.headers.get("access-control-allow-methods", "")
    for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
        assert method in allow_methods


def test_cors_no_origin_restrictive():
    """When ALLOWED_ORIGINS is empty, no CORS origin header is set."""
    response = client.get("/health")
    assert "access-control-allow-origin" not in response.headers
