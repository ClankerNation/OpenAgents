"""Request ID behaviour.

@generated-by Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04T13:05:00Z
@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import logging
import os
import pathlib
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.main import app  # noqa: E402
from api.middleware.request_id import HEADER, current_request_id  # noqa: E402
from api.models.database import Base, get_db  # noqa: E402

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


def test_response_carries_generated_header(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get(HEADER)
    assert len(r.headers[HEADER]) == 36  # uuid4


def test_ids_are_unique_per_request(client):
    ids = {client.get("/health").headers[HEADER] for _ in range(5)}
    assert len(ids) == 5


def test_client_supplied_id_is_preserved(client):
    r = client.get("/health", headers={HEADER: "trace-abc-123"})
    assert r.headers[HEADER] == "trace-abc-123"


def test_client_id_is_sanitised_when_unusable(client):
    r = client.get("/health", headers={HEADER: "bad id with spaces"})
    assert r.headers[HEADER] != "bad id with spaces"
    assert len(r.headers[HEADER]) == 36


def test_id_is_available_while_handling_and_cleared_after(client):
    seen = {}

    @app.get("/_probe")
    def probe():
        seen["during"] = current_request_id()
        return {"ok": True}

    client.get("/_probe")
    assert seen["during"] and seen["during"] != "-"
    assert current_request_id() == "-"


def test_log_lines_include_the_request_id(client, caplog):
    with caplog.at_level(logging.INFO):
        r = client.get("/health", headers={HEADER: "log-me-42"})
    assert r.headers[HEADER] == "log-me-42"
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert any(getattr(rec, "request_id", None) == "log-me-42" for rec in caplog.records)
    assert "health" in joined
