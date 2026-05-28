"""Tests for audit logging system."""

import pytest
import sys
import os
import jwt
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.models.database as db_module
from api.models.database import Base, get_db, AuditLog, User, Agent, Task
from api.middleware.auth import JWT_SECRET, JWT_ALGORITHM

TEST_DATABASE_URL = "sqlite:///./test_audit.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    original = db_module.get_db
    db_module.get_db = override_get_db
    yield
    db_module.get_db = original
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_user(db_session):
    user = User(id=1, address="0x1234567890abcdef", username="testuser")
    db_session.add(user)
    db_session.commit()
    return user


def _make_jwt(user_id: str = "1") -> str:
    payload = {
        "sub": user_id,
        "address": "0x1234567890abcdef",
        "roles": [],
        "type": "access",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _get_client():
    from api.main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


class TestAuditLogCreation:
    def test_agent_create_logs_audit(self, sample_user):
        client = _get_client()
        token = _make_jwt()
        response = client.post(
            "/agents/",
            json={"name": "Test Agent", "model_type": "gpt-4"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        db = TestingSessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "agent.create").all()
        assert len(logs) == 1
        assert logs[0].actor_id == "1"
        assert logs[0].target_type == "agent"
        assert logs[0].after_value["name"] == "Test Agent"
        db.close()

    def test_task_create_logs_audit(self, sample_user, db_session):
        client = _get_client()
        token = _make_jwt()
        response = client.post(
            "/tasks/",
            json={"title": "Test Task", "description": "Test", "reward_amount": 100},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        db = TestingSessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "task.create").all()
        assert len(logs) == 1
        assert logs[0].after_value["title"] == "Test Task"
        db.close()


class TestAuditLogQuery:
    def test_query_all_logs(self, sample_user, db_session):
        for i in range(5):
            log = AuditLog(
                action=f"test.action.{i}",
                actor_id="1",
                target_type="test",
                target_id=str(i),
                timestamp=datetime.utcnow(),
            )
            db_session.add(log)
        db_session.commit()

        client = _get_client()
        token = _make_jwt()
        response = client.get(
            "/admin/audit-log",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_filter_by_actor(self, sample_user, db_session):
        for i in range(3):
            db_session.add(AuditLog(
                action="test", actor_id=str(i % 2),
                timestamp=datetime.utcnow(),
            ))
        db_session.commit()

        client = _get_client()
        token = _make_jwt()
        response = client.get(
            "/admin/audit-log?actor=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert all(entry["actor_id"] == "0" for entry in data)

    def test_filter_by_action(self, sample_user, db_session):
        db_session.add(AuditLog(action="type_a", actor_id="1", timestamp=datetime.utcnow()))
        db_session.add(AuditLog(action="type_b", actor_id="1", timestamp=datetime.utcnow()))
        db_session.commit()

        client = _get_client()
        token = _make_jwt()
        response = client.get(
            "/admin/audit-log?action=type_a",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "type_a"

    def test_pagination(self, sample_user, db_session):
        for i in range(10):
            db_session.add(AuditLog(
                action="test", actor_id="1",
                timestamp=datetime.utcnow(),
            ))
        db_session.commit()

        client = _get_client()
        token = _make_jwt()
        response = client.get(
            "/admin/audit-log?limit=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestAuditLogImmutability:
    def test_audit_log_has_no_update_endpoint(self):
        client = _get_client()
        token = _make_jwt()
        response = client.put(
            "/admin/audit-log/1",
            json={"action": "tampered"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (404, 405)

    def test_audit_log_has_no_delete_endpoint(self):
        client = _get_client()
        token = _make_jwt()
        response = client.delete(
            "/admin/audit-log/1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (404, 405)
