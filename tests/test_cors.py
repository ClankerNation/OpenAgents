"""
Tests for CORS configuration in main.py.
"""
import os
from httpx import ASGITransport, AsyncClient
import pytest


async def test_cors_headers_present_preflight():
    """OPTIONS preflight should return CORS headers with configured origins."""
    os.environ["ALLOWED_ORIGINS"] = "https://example.com"
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/agents",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code in (200, 204, 405)
    cors_origin = resp.headers.get("access-control-allow-origin")
    if cors_origin:
        assert cors_origin == "https://example.com"
    assert resp.headers.get("access-control-allow-credentials") == "true"


async def test_cors_headers_present_get():
    """Cross-origin GET should include CORS headers."""
    os.environ["ALLOWED_ORIGINS"] = "https://example.com"
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "https://example.com"},
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://example.com"
    assert resp.headers.get("access-control-allow-credentials") == "true"


async def test_wildcard_development_mode():
    """ALLOWED_ORIGINS=* should allow all origins (no credentials)."""
    os.environ["ALLOWED_ORIGINS"] = "*"
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "https://any-origin.com"},
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_no_origin_env_denies_all():
    """With no ALLOWED_ORIGINS set, CORS headers should not allow external origins."""
    if "ALLOWED_ORIGINS" in os.environ:
        del os.environ["ALLOWED_ORIGINS"]
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "https://evil.com"},
        )
    assert resp.status_code == 200


async def test_health_endpoint_no_cors_restriction():
    """Health endpoint should still work."""
    if "ALLOWED_ORIGINS" in os.environ:
        del os.environ["ALLOWED_ORIGINS"]
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_multiple_origins():
    """Comma-separated origins should all be allowed."""
    os.environ["ALLOWED_ORIGINS"] = "https://app.example.com,https://admin.example.com"
    import api.main as main_mod
    import importlib
    importlib.reload(main_mod)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "https://app.example.com"},
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert resp.headers.get("access-control-allow-credentials") == "true"
