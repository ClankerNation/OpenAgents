from fastapi.responses import JSONResponse

import api.health as health


def reset_cache():
    health._HEALTH_CACHE = None
    health._HEALTH_CACHE_AT = 0.0


def test_health_payload_contains_component_status_and_latency(monkeypatch):
    reset_cache()
    monkeypatch.setattr(health, "check_database", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_rpc", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_disk", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_memory", lambda: {"status": "healthy"})

    payload = health.cached_health()

    assert payload["status"] == "healthy"
    assert payload["cached"] is False
    assert set(payload["components"]) == {"db", "rpc", "disk", "memory"}
    assert all("latency_ms" in component for component in payload["components"].values())


def test_overall_status_reflects_worst_component(monkeypatch):
    reset_cache()
    monkeypatch.setattr(health, "check_database", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_rpc", lambda: {"status": "unhealthy", "details": "down"})
    monkeypatch.setattr(health, "check_disk", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_memory", lambda: {"status": "healthy"})

    payload = health.cached_health()

    assert payload["status"] == "unhealthy"
    assert payload["components"]["rpc"]["status"] == "unhealthy"


def test_health_response_uses_503_when_unhealthy(monkeypatch):
    reset_cache()
    monkeypatch.setattr(health, "cached_health", lambda: {"status": "unhealthy", "components": {}})

    response = health.health_response()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


def test_health_result_is_cached(monkeypatch):
    reset_cache()
    calls = {"count": 0}

    def collect():
        calls["count"] += 1
        return {"status": "healthy", "components": {}, "timestamp": "now", "cache_ttl_seconds": 10}

    monkeypatch.setattr(health, "collect_health", collect)

    first = health.cached_health()
    second = health.cached_health()

    assert calls["count"] == 1
    assert first["cached"] is False
    assert second["cached"] is True
