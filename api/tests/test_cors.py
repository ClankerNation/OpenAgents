"""CORS policy behaviour.

@contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@platform-config full verbatim block: see the header of api/cors.py
@env os=windows arch=x86_64 home_dir=C:\\Users\\2 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
@timestamp 2026-11-04T15:10:00Z
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.cors import cors_settings, parse_origins
from api.main import app as real_app

ORIGIN = "https://app.example.com"


@pytest.fixture
def build(monkeypatch):
    """Fresh app per test so middleware is configured from the env under test."""

    def _build():
        app = FastAPI()

        @app.get("/thing")
        def thing():
            return {"ok": True}

        from api.cors import configure_cors

        configure_cors(app)
        return TestClient(app)

    return _build


def test_preflight_gets_headers(build, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    c = build()
    r = c.options(
        "/thing",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "POST" in r.headers["access-control-allow-methods"]


def test_cross_origin_get_is_allowed(build, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    r = build().get("/thing", headers={"Origin": ORIGIN})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_unlisted_origin_gets_no_allow_header(build, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    r = build().get("/thing", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_origins_are_comma_separated_and_normalised(build, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", f" {ORIGIN}/ , http://localhost:3000 ")
    c = build()
    for origin in (ORIGIN, "http://localhost:3000"):
        assert c.get("/thing", headers={"Origin": origin}).headers[
            "access-control-allow-origin"
        ] == origin


def test_wildcard_in_development_echoes_the_origin(build, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("ENV", "development")
    r = build().get("/thing", headers={"Origin": ORIGIN})
    # echoed, not literal '*', so credentials are usable
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


def test_production_default_is_restrictive(build, monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("ENV", "production")
    r = build().get("/thing", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in r.headers


def test_development_default_allows_local_dev_servers(build, monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("ENV", "development")
    r = build().get("/thing", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_methods_and_headers_cover_the_api(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    settings = cors_settings()
    assert set(settings["allow_methods"]) == {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
    assert "Authorization" in settings["allow_headers"]
    assert settings["allow_credentials"] is True


def test_parse_origins_handles_blanks():
    assert parse_origins(" a ,, b ,") == ["a", "b"]
    assert parse_origins(None) == []


def test_real_app_is_configured():
    """The shipped app carries the policy: default here is production, so an unlisted dev origin
    is refused at preflight rather than silently allowed."""
    c = TestClient(real_app)
    r = c.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 400  # middleware is mounted and rejecting
    assert "access-control-allow-origin" not in c.get("/health").headers
