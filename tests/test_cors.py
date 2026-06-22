import importlib

from fastapi.testclient import TestClient


def load_app(monkeypatch, allowed_origins=None, environment="production"):
    if allowed_origins is None:
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setenv("ENVIRONMENT", environment)

    import api.main as main

    return importlib.reload(main).app


def test_cors_allows_configured_origin_with_credentials(monkeypatch):
    app = load_app(monkeypatch, "https://app.openagents.dev")
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://app.openagents.dev",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.openagents.dev"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]


def test_cors_rejects_unconfigured_origin_in_production(monkeypatch):
    app = load_app(monkeypatch, "https://app.openagents.dev")
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_is_development_only(monkeypatch):
    production_app = load_app(monkeypatch, "*", environment="production")
    production_client = TestClient(production_app)
    production_response = production_client.options(
        "/health",
        headers={"Origin": "https://any.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in production_response.headers

    development_app = load_app(monkeypatch, "*", environment="development")
    development_client = TestClient(development_app)
    development_response = development_client.options(
        "/health",
        headers={"Origin": "https://any.example", "Access-Control-Request-Method": "GET"},
    )

    assert development_response.headers["access-control-allow-origin"] == "https://any.example"
