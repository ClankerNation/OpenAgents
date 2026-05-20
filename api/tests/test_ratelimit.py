from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.ratelimit import EndpointLimit, RateLimitConfig, RateLimitMiddleware


def build_client(tmp_path, config: RateLimitConfig, client_host: str = "127.0.0.1") -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    @app.get("/special")
    async def special():
        return {"ok": True}

    return TestClient(app, client=(client_host, 12345))


def test_x_forwarded_for_is_ignored_without_trusted_proxy(tmp_path):
    db_path = str(tmp_path / "ratelimit.sqlite3")
    client = build_client(tmp_path, RateLimitConfig(requests_per_window=1, window_seconds=60, storage_path=db_path))

    assert client.get("/limited", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    response = client.get("/limited", headers={"X-Forwarded-For": "2.2.2.2"})

    assert response.status_code == 429


def test_x_forwarded_for_is_used_for_trusted_proxy(tmp_path):
    db_path = str(tmp_path / "ratelimit.sqlite3")
    client = build_client(
        tmp_path,
        RateLimitConfig(
            requests_per_window=1,
            window_seconds=60,
            storage_path=db_path,
            trusted_proxy_cidrs=("10.0.0.0/8",),
        ),
        client_host="10.0.0.1",
    )

    assert client.get("/limited", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get("/limited", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_rate_limit_state_survives_middleware_restart(tmp_path):
    db_path = str(tmp_path / "ratelimit.sqlite3")
    config = RateLimitConfig(requests_per_window=1, window_seconds=60, storage_path=db_path)
    first_client = build_client(tmp_path, config)
    assert first_client.get("/limited").status_code == 200

    second_client = build_client(tmp_path, config)
    response = second_client.get("/limited")

    assert response.status_code == 429


def test_endpoint_specific_limits(tmp_path):
    db_path = str(tmp_path / "ratelimit.sqlite3")
    client = build_client(
        tmp_path,
        RateLimitConfig(
            requests_per_window=10,
            window_seconds=60,
            storage_path=db_path,
            endpoint_limits={"/special": EndpointLimit(requests_per_window=1, window_seconds=60)},
        ),
    )

    assert client.get("/special").status_code == 200
    assert client.get("/special").status_code == 429
    assert client.get("/limited").status_code == 200
