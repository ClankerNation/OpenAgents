import importlib
import os

from fastapi.testclient import TestClient


def load_app(monkeypatch, allowed_origins="https://frontend.example", env="production"):
    monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setenv("ENV", env)
    import api.main as main

    return importlib.reload(main).app


def test_cors_preflight_allows_configured_origin(monkeypatch):
    app = load_app(monkeypatch)
    client = TestClient(app)

    response = client.options(
        "/agents",
        headers={
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_cross_origin_get_includes_cors_headers(monkeypatch):
    app = load_app(monkeypatch)
    client = TestClient(app)

    response = client.get("/agents", headers={"Origin": "https://frontend.example"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wildcard_origin_is_not_allowed_in_production(monkeypatch):
    app = load_app(monkeypatch, allowed_origins="*", env="production")
    client = TestClient(app)

    response = client.get("/agents", headers={"Origin": "https://frontend.example"})

    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_is_allowed_in_development(monkeypatch):
    app = load_app(monkeypatch, allowed_origins="*", env="development")
    client = TestClient(app)

    response = client.get("/agents", headers={"Origin": "https://frontend.example"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
