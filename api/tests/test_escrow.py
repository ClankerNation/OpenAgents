"""Tests for escrow auto-refund functionality."""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.main import app
from api.models.database import Base, get_db, Payment, Task, User

TEST_DATABASE_URL = "sqlite:///./test_escrow.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
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


@pytest.fixture
def sample_task(db_session, sample_user):
    task = Task(
        id=1,
        title="Test Task",
        description="Test",
        reward_amount=100.0,
        creator_id=sample_user.id,
        status="open",
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.commit()
    return task


class TestFreshEscrowNotTouched:
    def test_recent_escrow_not_refunded(self, db_session, sample_task):
        payment = Payment(
            task_id=sample_task.id,
            from_address="0xabc",
            amount=50.0,
            status="escrowed",
            created_at=datetime.utcnow(),
        )
        db_session.add(payment)
        db_session.commit()

        client = TestClient(app)
        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        data = response.json()
        assert data["refunded_count"] == 0

        db_session.refresh(payment)
        assert payment.status == "escrowed"


class TestExpiredEscrowRefunded:
    def test_expired_escrow_gets_refunded(self, db_session, sample_task):
        old_time = datetime.utcnow() - timedelta(days=31)
        payment = Payment(
            task_id=sample_task.id,
            from_address="0xabc",
            amount=75.0,
            status="escrowed",
            created_at=old_time,
        )
        db_session.add(payment)
        db_session.commit()
        payment_id = payment.id

        client = TestClient(app)
        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        data = response.json()
        assert data["refunded_count"] == 1
        assert len(data["refunds"]) == 1
        assert data["refunds"][0]["escrow_id"] == payment_id
        assert data["refunds"][0]["amount"] == 75.0
        assert data["refunds"][0]["refunded_to"] == "0xabc"

        db_session.refresh(payment)
        assert payment.status == "refunded"
        assert payment.to_address == "0xabc"

    def test_escrow_at_exact_boundary_not_refunded(self, db_session, sample_task):
        boundary_time = datetime.utcnow() - timedelta(days=30) + timedelta(seconds=10)
        payment = Payment(
            task_id=sample_task.id,
            from_address="0xabc",
            amount=50.0,
            status="escrowed",
            created_at=boundary_time,
        )
        db_session.add(payment)
        db_session.commit()

        client = TestClient(app)
        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        data = response.json()
        assert data["refunded_count"] == 0

    def test_already_claimed_not_refunded(self, db_session, sample_task):
        old_time = datetime.utcnow() - timedelta(days=31)
        payment = Payment(
            task_id=sample_task.id,
            from_address="0xabc",
            amount=50.0,
            status="claimed",
            created_at=old_time,
        )
        db_session.add(payment)
        db_session.commit()

        client = TestClient(app)
        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        data = response.json()
        assert data["refunded_count"] == 0


class TestMultipleExpiredEscrows:
    def test_all_expired_escrows_refunded(self, db_session, sample_task):
        old_time = datetime.utcnow() - timedelta(days=31)
        for i in range(3):
            payment = Payment(
                task_id=sample_task.id,
                from_address=f"0x{i}",
                amount=10.0 * (i + 1),
                status="escrowed",
                created_at=old_time,
            )
            db_session.add(payment)
        db_session.commit()

        client = TestClient(app)
        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        data = response.json()
        assert data["refunded_count"] == 3
