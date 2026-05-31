from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from models.database import Agent, AuditLog, Base, User, get_db
from routes.admin import router as admin_router


@pytest.fixture()
def test_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(admin_router)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    seed = TestingSessionLocal()
    seed.add(User(id=1, address="0x1111111111111111111111111111111111111111", username="alice"))
    seed.add(
        Agent(
            id=1,
            name="agent-1",
            description="baseline",
            model_type="gpt-4",
            config={"temperature": 0.2},
            owner_id=1,
        )
    )
    seed.commit()
    seed.close()

    return client, TestingSessionLocal


def test_admin_action_creates_audit_log_with_before_after(test_context):
    client, SessionLocal = test_context

    response = client.patch(
        "/admin/users/1",
        json={"username": "alice-updated"},
        headers={"X-Admin-Actor": "alice-admin", "X-Admin-Role": "admin"},
    )

    assert response.status_code == 200

    db = SessionLocal()
    logs = db.query(AuditLog).all()
    db.close()

    assert len(logs) == 1
    assert logs[0].action == "user.update"
    assert logs[0].actor == "alice-admin"
    assert logs[0].before_values == {"username": "alice"}
    assert logs[0].after_values == {"username": "alice-updated"}


def test_audit_log_query_supports_actor_action_and_date_filters(test_context):
    client, _ = test_context

    client.patch(
        "/admin/users/1",
        json={"username": "alice-v2"},
        headers={"X-Admin-Actor": "alice-admin", "X-Admin-Role": "admin"},
    )
    client.patch(
        "/admin/agents/1",
        json={"model_type": "gpt-4.1"},
        headers={"X-Admin-Actor": "bob-admin", "X-Admin-Role": "admin"},
    )

    by_actor = client.get("/admin/audit-log", params={"actor": "alice-admin"})
    assert by_actor.status_code == 200
    assert len(by_actor.json()) == 1
    assert by_actor.json()[0]["action"] == "user.update"

    by_action = client.get("/admin/audit-log", params={"action": "agent.update"})
    assert by_action.status_code == 200
    assert len(by_action.json()) == 1
    assert by_action.json()[0]["actor"] == "bob-admin"

    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    by_future = client.get("/admin/audit-log", params={"start_date": future})
    assert by_future.status_code == 200
    assert by_future.json() == []


def test_audit_log_records_are_immutable(test_context):
    _, SessionLocal = test_context
    db = SessionLocal()
    db.add(
        AuditLog(
            action="user.update",
            actor="seed-admin",
            target="user:1",
            before_values={"username": "alice"},
            after_values={"username": "alice-v3"},
            ip="127.0.0.1",
        )
    )
    db.commit()

    log = db.query(AuditLog).first()
    log.action = "changed"
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()

    with pytest.raises(ValueError):
        db.delete(log)
        db.commit()
    db.close()
