import importlib
import sys

from fastapi.testclient import TestClient


def load_main(monkeypatch, allowed_origins, environment="production"):
    monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setenv("APP_ENV", environment)
    sys.modules.pop("api.main", None)
    return importlib.import_module("api.main")


def test_preflight_allows_configured_origin(monkeypatch):
    main = load_main(monkeypatch, "https://app.example.com")
    client = TestClient(main.app)

    response = client.options(
        "/agents",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cross_origin_get_includes_cors_headers(monkeypatch):
    main = load_main(monkeypatch, "https://dashboard.example.com")
    client = TestClient(main.app)

    response = client.get("/health", headers={"Origin": "https://dashboard.example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wildcard_origin_is_restricted_in_production(monkeypatch):
    main = load_main(monkeypatch, "*", environment="production")
    client = TestClient(main.app)

    response = client.get("/health", headers={"Origin": "https://unknown.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_is_allowed_in_development(monkeypatch):
    main = load_main(monkeypatch, "*", environment="development")
    client = TestClient(main.app)

    response = client.get("/health", headers={"Origin": "https://local.example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://local.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
