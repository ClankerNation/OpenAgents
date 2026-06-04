import importlib
import sys

from fastapi.testclient import TestClient


MODULE_NAME = "api.main"


def load_app(monkeypatch, *, allowed_origins=None, cors_allowed_origins=None, env="production"):
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    if allowed_origins is not None:
        monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    if cors_allowed_origins is not None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", cors_allowed_origins)

    sys.modules.pop(MODULE_NAME, None)
    import api.main as main

    return importlib.reload(main).app


def preflight(client, origin="https://frontend.example", method="GET"):
    return client.options(
        "/agents",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_cors_preflight_allows_configured_origin(monkeypatch):
    app = load_app(monkeypatch, allowed_origins="https://frontend.example")
    client = TestClient(app)

    response = preflight(client)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    allowed_methods = response.headers["access-control-allow-methods"]
    for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
        assert method in allowed_methods


def test_cross_origin_get_includes_cors_headers(monkeypatch):
    app = load_app(monkeypatch, allowed_origins="https://frontend.example")
    client = TestClient(app)

    response = client.get("/agents", headers={"Origin": "https://frontend.example"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_comma_separated_origins_are_normalized(monkeypatch):
    app = load_app(
        monkeypatch,
        allowed_origins=" https://frontend.example/ , https://admin.example ",
    )
    client = TestClient(app)

    response = preflight(client, origin="https://frontend.example")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"


def test_cors_allowed_origins_alias_is_supported(monkeypatch):
    app = load_app(monkeypatch, cors_allowed_origins="https://alias.example")
    client = TestClient(app)

    response = preflight(client, origin="https://alias.example")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://alias.example"


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
    assert response.headers["access-control-allow-credentials"] == "true"


def test_production_without_env_uses_restrictive_default_frontend_origins(monkeypatch):
    app = load_app(monkeypatch, env="production")
    client = TestClient(app)

    allowed = client.get("/agents", headers={"Origin": "https://app.openagents.com"})
    blocked = client.get("/agents", headers={"Origin": "https://evil.example"})

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.openagents.com"
    assert "access-control-allow-origin" not in blocked.headers
