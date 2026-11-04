"""Endpoint validation and SSRF protection on agent registration.

@generated-by Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04T13:30:00Z
@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import os
import pathlib
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.main import app  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402
from api.models.database import Base, get_db  # noqa: E402
from api.services import endpoint_validation as ev  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def override_get_db():
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth():
    token = create_access_token({"sub": "1", "address": "0xowner", "roles": ["user"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(ev, "resolve_host", lambda host: ["93.184.216.34"])
    calls = []

    def fake_head(url):
        calls.append(url)

    monkeypatch.setattr(ev, "head_probe", fake_head)
    return calls


def register(client, auth, url):
    return client.post("/agents/", json={"name": "a", "endpoint": url}, headers=auth)


def test_valid_url_is_stored(client, auth, public_dns):
    r = register(client, auth, "https://agent.example.com/hook")
    assert r.status_code == 200, r.text
    assert r.json()["endpoint"] == "https://agent.example.com/hook"
    assert public_dns == ["https://agent.example.com/hook"]  # HEAD probe actually ran


def test_invalid_format_rejected(client, auth, public_dns):
    for bad in ("not-a-url", "ftp://example.com", "https://", "example.com/hook"):
        r = register(client, auth, bad)
        assert r.status_code == 400, (bad, r.text)
        assert r.json()["detail"]


def test_private_addresses_blocked(client, auth, monkeypatch):
    for addr in ("10.1.2.3", "192.168.0.10", "127.0.0.1", "::1"):
        monkeypatch.setattr(ev, "resolve_host", lambda host, a=addr: [a])
        monkeypatch.setattr(ev, "head_probe", lambda url: None)
        r = register(client, auth, "https://internal.example.com")
        assert r.status_code == 400, (addr, r.text)
        assert "private" in r.json()["detail"]


def test_hostname_with_mixed_public_and_private_is_rejected(client, auth, monkeypatch):
    monkeypatch.setattr(ev, "resolve_host", lambda host: ["93.184.216.34", "10.0.0.5"])
    monkeypatch.setattr(ev, "head_probe", lambda url: None)
    assert register(client, auth, "https://split.example.com").status_code == 400


def test_unresolvable_host_rejected(client, auth, monkeypatch):
    import socket

    def boom(host):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ev, "resolve_host", boom)
    r = register(client, auth, "https://nope.invalid")
    assert r.status_code == 400
    assert "resolve" in r.json()["detail"]


def test_timeout_returns_promptly_with_error(client, auth, monkeypatch):
    monkeypatch.setattr(ev, "resolve_host", lambda host: ["93.184.216.34"])

    def slow(url):
        raise httpx.TimeoutException("too slow")

    monkeypatch.setattr(ev, "head_probe", slow)
    r = register(client, auth, "https://slow.example.com")
    assert r.status_code == 400
    assert "5s" in r.json()["detail"]


def test_unreachable_endpoint_rejected(client, auth, monkeypatch):
    monkeypatch.setattr(ev, "resolve_host", lambda host: ["93.184.216.34"])

    def refused(url):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(ev, "head_probe", refused)
    r = register(client, auth, "https://down.example.com")
    assert r.status_code == 400
    assert "unreachable" in r.json()["detail"]


def test_credentials_and_overlong_urls_rejected(client, auth, public_dns):
    assert register(client, auth, "https://user:pw@example.com").status_code == 400
    assert register(client, auth, "https://example.com/" + "a" * 2100).status_code == 400
