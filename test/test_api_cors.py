"""
@contributor-info Codex Agent xyjk0511
@platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
@runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
@date 2026-05-31T00:00:00-07:00
"""

import importlib
import sys

from fastapi.testclient import TestClient


def load_client(monkeypatch, allowed_origins, environment="production"):
    monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setenv("ENVIRONMENT", environment)
    sys.modules.pop("api.main", None)
    module = importlib.import_module("api.main")
    return TestClient(module.app)


def test_preflight_options_includes_cors_headers(monkeypatch):
    client = load_client(monkeypatch, "https://frontend.example")

    response = client.options(
        "/health",
        headers={
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]


def test_cross_origin_get_includes_cors_headers(monkeypatch):
    client = load_client(monkeypatch, "https://frontend.example,https://admin.example")

    response = client.get("/health", headers={"Origin": "https://admin.example"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://admin.example"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wildcard_origin_is_restricted_outside_development(monkeypatch):
    client = load_client(monkeypatch, "*", environment="production")

    response = client.get("/health", headers={"Origin": "https://frontend.example"})

    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_config_allows_origins_in_development(monkeypatch):
    client = load_client(monkeypatch, "*", environment="development")

    response = client.get("/health", headers={"Origin": "https://frontend.example"})

    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"
