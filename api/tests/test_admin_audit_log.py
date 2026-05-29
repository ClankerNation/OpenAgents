import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import AuditLog, Base, get_db
from api.routes.admin import admin_required, create_audit_log, router


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[admin_required] = lambda: {"id": 1, "roles": ["admin"]}
    return TestClient(app)


def test_create_audit_log(db_session):
    entry = create_audit_log(
        db_session,
        action="set_fee",
        actor="admin-1",
        target="registration_fee",
        before={"fee": 1},
        after={"fee": 2},
        ip="203.0.113.10",
    )

    stored = db_session.query(AuditLog).filter(AuditLog.id == entry.id).one()
    assert stored.action == "set_fee"
    assert stored.actor == "admin-1"
    assert stored.before == {"fee": 1}
    assert stored.after == {"fee": 2}
    assert stored.ip == "203.0.113.10"


def test_query_audit_log_filters(client, db_session):
    create_audit_log(db_session, action="set_fee", actor="admin-1", target="fee")
    create_audit_log(db_session, action="delete_user", actor="admin-2", target="user:9")

    response = client.get("/admin/audit-log", params={"actor": "admin-1", "action": "set_fee"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["actor"] == "admin-1"
    assert payload[0]["action"] == "set_fee"


def test_audit_log_records_are_immutable(db_session):
    entry = create_audit_log(
        db_session,
        action="set_fee",
        actor="admin-1",
        target="registration_fee",
    )

    entry.action = "tamper"
    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()

    db_session.rollback()
    db_session.delete(entry)
    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()
