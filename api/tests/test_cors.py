import importlib

from fastapi.testclient import TestClient

import api.cors as cors
import api.main as main


def reload_app(monkeypatch, allowed_origins: str, environment: str = "production"):
    monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setenv("ENVIRONMENT", environment)
    importlib.reload(cors)
    return importlib.reload(main).app


def test_preflight_allows_configured_origin(monkeypatch):
    app = reload_app(monkeypatch, "https://app.example.com")
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]


def test_cross_origin_get_has_cors_headers(monkeypatch):
    app = reload_app(monkeypatch, "https://app.example.com")
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "https://app.example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wildcard_is_not_allowed_in_production(monkeypatch):
    app = reload_app(monkeypatch, "*", environment="production")
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_wildcard_is_allowed_in_development(monkeypatch):
    app = reload_app(monkeypatch, "*", environment="development")
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "https://local.example"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://local.example"
    assert response.headers["access-control-allow-credentials"] == "true"
