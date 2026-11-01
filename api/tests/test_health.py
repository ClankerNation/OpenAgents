"""Tests for the enhanced /health endpoint (bounty issue #41)."""

from fastapi.testclient import TestClient

from ..main import app


client = TestClient(app)


def test_health_returns_200_when_components_healthy():
    """Health endpoint returns HTTP 200 and valid component structure."""
    response = client.get("/health")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert "timestamp" in data
    assert data["cache_ttl_seconds"] == 10

    components = data["components"]
    for name in ("db", "rpc", "disk", "memory"):
        assert name in components, f"missing component: {name}"
        comp = components[name]
        assert comp["status"] in ("healthy", "unhealthy")
        assert "latency_ms" in comp
        assert isinstance(comp["latency_ms"], (int, float))


def test_health_cache_control_header():
    """Response is cacheable for 10 seconds."""
    response = client.get("/health")
    cache_control = response.headers.get("cache-control", "")
    assert "max-age=10" in cache_control, f"unexpected cache-control: {cache_control}"


def test_health_response_shape():
    """Response matches the expected schema."""
    response = client.get("/health")
    data = response.json()

    # Overall status must be one of the allowed values
    assert data["status"] in ("healthy", "unhealthy")

    # Each component must have status and latency_ms
    for comp in data["components"].values():
        assert set(comp.keys()) >= {"status", "latency_ms"}


def test_health_overall_unhealthy_when_component_unhealthy(monkeypatch):
    """Overall status flips to unhealthy when any component is unhealthy."""
    from .. import main

    def fake_unhealthy():
        from ..main import ComponentStatus

        return ComponentStatus(
            status="unhealthy", latency_ms=10.0, detail="simulated failure"
        )

    monkeypatch.setattr(main, "_check_memory", fake_unhealthy)
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["memory"]["status"] == "unhealthy"
