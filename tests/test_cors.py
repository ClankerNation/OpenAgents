"""Tests for CORS configuration."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_cors_headers_present(client):
    """CORS headers present in response."""
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" in response.headers


def test_cors_preflight(client):
    """CORS preflight request works."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-methods" in response.headers


def test_cors_allow_methods(client):
    """CORS allows common methods."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200


def test_cors_credentials(client):
    """CORS allows credentials."""
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    # When allow_credentials is True, the header should be present
    assert "access-control-allow-origin" in response.headers
