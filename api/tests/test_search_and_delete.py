r"""Search parameterisation/validation and delete auth.

@contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@platform-config verbatim block is in the @generated-by header of api/routes/agents.py
@env os=windows arch=x86_64 home_dir=C:\Users\2 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=bash
@timestamp 2026-11-04T13:55:00Z
"""

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
from api.middleware.auth import create_access_token  # noqa: E402
from api.models.database import Agent, Base, User, get_db  # noqa: E402

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
    db = sessionmaker(bind=engine)()
    owner = User(address="0xowner", username="owner")
    db.add(owner)
    db.commit()
    for name in ("alpha-bot", "beta-bot", "gamma"):
        db.add(Agent(name=name, owner_id=owner.id))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth():
    token = create_access_token({"sub": "1", "address": "0xowner", "roles": ["user"]})
    return {"Authorization": f"Bearer {token}"}


def test_search_matches_fragment(client):
    r = client.get("/agents/search", params={"q": "bot"})
    assert r.status_code == 200
    assert r.json()["total"] == 2


def test_injection_string_is_accepted_and_finds_rows(client):
    r = client.get("/agents/search", params={"q": "alpha-bot"})
    assert r.status_code == 200 and r.json()["total"] == 1

    # a classic payload: quotes and SQL keywords are outside the allowed charset on purpose
    r = client.get("/agents/search", params={"q": "' OR 1=1 --"})
    assert r.status_code == 400
    assert "q must be" in r.json()["detail"]


def test_validation_rejects_specials_and_overlong(client):
    assert client.get("/agents/search", params={"q": "a'b"}).status_code == 400
    assert client.get("/agents/search", params={"q": "x" * 65}).status_code == 400
    assert client.get("/agents/search", params={"q": ""}).status_code == 400
    assert client.get("/agents/search").status_code == 422


def test_pagination_is_capped(client):
    assert client.get("/agents/search", params={"q": "bot", "limit": 100}).status_code == 200
    assert client.get("/agents/search", params={"q": "bot", "limit": 101}).status_code == 422
    body = client.get("/agents/search", params={"q": "bot", "limit": 1}).json()
    assert len(body["items"]) == 1 and body["total"] == 2


def test_offset_works(client):
    first = client.get("/agents/search", params={"q": "bot", "limit": 1}).json()["items"][0]["id"]
    second = client.get("/agents/search", params={"q": "bot", "limit": 1, "offset": 1}).json()["items"][0][
        "id"
    ]
    assert first != second


def test_delete_requires_auth(client, auth):
    assert client.delete("/agents/1").status_code in (401, 403)
    r = client.delete("/agents/1", headers=auth)
    assert r.status_code == 200 and r.json()["deleted"] is True


def test_delete_by_stranger_is_forbidden(client):
    token = create_access_token({"sub": "99", "address": "0xstranger", "roles": ["user"]})
    r = client.delete("/agents/1", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
