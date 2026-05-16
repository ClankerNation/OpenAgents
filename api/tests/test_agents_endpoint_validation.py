import sys
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.routes import agents


def test_valid_url_passes_with_public_ip(monkeypatch):
    monkeypatch.setattr(
        agents.socket,
        "getaddrinfo",
        lambda host, port: [
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ],
    )

    out = agents._validate_and_normalize_public_url("https://example.com/callback")
    assert out == "https://example.com/callback"


def test_invalid_url_format_rejected():
    with pytest.raises(HTTPException) as exc:
        agents._validate_and_normalize_public_url("ftp://example.com/resource")
    assert exc.value.status_code == 422
    assert "http/https" in exc.value.detail


def test_private_ip_rejected(monkeypatch):
    monkeypatch.setattr(
        agents.socket,
        "getaddrinfo",
        lambda host, port: [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ],
    )

    with pytest.raises(HTTPException) as exc:
        agents._validate_and_normalize_public_url("http://localhost:8080")
    assert exc.value.status_code == 422
    assert "private/internal IP" in exc.value.detail


@pytest.mark.asyncio
async def test_head_timeout_rejected(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def head(self, url):
            raise agents.httpx.TimeoutException("timed out")

    monkeypatch.setattr(agents.httpx, "AsyncClient", FakeClient)

    with pytest.raises(HTTPException) as exc:
        await agents._ensure_reachable("https://example.com")
    assert exc.value.status_code == 422
    assert "timed out" in exc.value.detail
