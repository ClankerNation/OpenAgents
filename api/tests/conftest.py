"""Shared test fixtures: one engine for the whole session, one client shape.

Every module used to build its own engine and override `get_db`, so whichever module was imported
last won the override while the other module's `drop_all` had already emptied it.

@fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\Program Files\Git\bin\bash.exe
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
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth():
    from api.middleware.auth import create_access_token

    token = create_access_token({"sub": "1", "address": "0xa", "roles": ["user"]})
    return {"Authorization": f"Bearer {token}"}
