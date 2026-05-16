"""Tests for payments.py — escrow expiry auto-refund."""
import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set a test JWT secret before importing auth middleware
os.environ["JWT_SECRET"] = "test-secret-key-for-tests-only"

from fastapi import FastAPI, Depends
from ..models.database import Base, get_db, User, Task, Payment
from ..middleware.auth import get_current_user
from ..routes.payments import router


# ── Test database setup ──────────────────────────────────────────────────────

@pytest.fixture
def engine():
    """Create fresh in-memory SQLite database per test."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine):
    """Fresh session per test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ── FastAPI TestClient with overridden deps ──────────────────────────────────

@pytest.fixture
def client(db_session):
    app = FastAPI()

    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_current_user():
        return {"id": 1, "address": "0xTestPayerAddress00000000000000", "roles": []}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(router)

    return TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_user(session):
    """Create a test user in the database."""
    user = User(id=1, address="0xTestPayerAddress00000000000000", username="test_payer")
    session.add(user)
    session.commit()
    return user


def _create_task(session, creator_id=1, status="open"):
    """Create a test task."""
    task = Task(
        id=1,
        title="Test Task",
        description="A test task for escrow testing",
        reward_amount=100.0,
        status=status,
        creator_id=creator_id,
    )
    session.add(task)
    session.commit()
    return task


# ── Tests ────────────────────────────────────────────────────────────────────

class TestEscrowExpiryAutoRefund:

    def test_fresh_escrow_not_affected(self, client, db_session):
        """A just-deposited escrow with a future release_time is not refunded."""
        _create_user(db_session)
        _create_task(db_session)

        future_release = (datetime.utcnow() + timedelta(days=60)).isoformat()

        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 100.0,
            "release_time": future_release,
        })
        assert deposit_resp.status_code == 200
        assert deposit_resp.json()["status"] == "escrowed"

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1
        assert data["refunded"] == 0

        payment = db_session.query(Payment).filter(Payment.id == 1).first()
        assert payment.status == "escrowed"

    def test_expired_escrow_refunded(self, client, db_session):
        """An escrow past its 30-day grace period is refunded to the payer."""
        _create_user(db_session)
        _create_task(db_session)

        past_release = (datetime.utcnow() - timedelta(days=60)).isoformat()

        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 200.0,
            "release_time": past_release,
        })
        assert deposit_resp.status_code == 200
        payment_id = deposit_resp.json()["payment_id"]

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1
        assert data["refunded"] == 1

        refund = data["refunds"][0]
        assert refund["payment_id"] == payment_id
        assert refund["amount"] == 200.0
        assert refund["payer"] == "0xTestPayerAddress00000000000000"

        payment = db_session.query(Payment).filter(Payment.id == payment_id).first()
        assert payment.status == "refunded"
        assert payment.to_address == "0xTestPayerAddress00000000000000"

    def test_escrow_without_release_time_ignored(self, client, db_session):
        """Escrows without a release_time are skipped (never expire)."""
        _create_user(db_session)
        _create_task(db_session)

        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 50.0,
        })
        assert deposit_resp.status_code == 200

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 0
        assert data["refunded"] == 0

    def test_only_escrowed_status_processed(self, client, db_session):
        """Already-refunded payments are not re-processed."""
        _create_user(db_session)
        _create_task(db_session)

        past_release = (datetime.utcnow() - timedelta(days=60)).isoformat()

        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 300.0,
            "release_time": past_release,
        })
        assert deposit_resp.status_code == 200

        resp1 = client.post("/payments/process-expired")
        assert resp1.json()["refunded"] == 1

        resp2 = client.post("/payments/process-expired")
        assert resp2.json()["refunded"] == 0

    def test_expired_at_computed_correctly(self, client, db_session):
        """The expired_at property is exactly release_time + 30 days."""
        _create_user(db_session)
        _create_task(db_session)

        release = datetime(2026, 1, 1, 0, 0, 0)
        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 10.0,
            "release_time": release.isoformat(),
        })
        assert deposit_resp.status_code == 200

        payment = db_session.query(Payment).filter(Payment.id == 1).first()
        assert payment.expired_at == datetime(2026, 1, 31, 0, 0, 0)
        assert payment.is_expired is True  # May 2026 > Jan 31 2026

    def test_no_release_time_expired_at_is_none(self, client, db_session):
        """Escrows without release_time have expired_at=None and is_expired=False."""
        _create_user(db_session)
        _create_task(db_session)

        deposit_resp = client.post("/payments/escrow/deposit", json={
            "task_id": 1,
            "amount": 10.0,
        })
        assert deposit_resp.status_code == 200

        payment = db_session.query(Payment).filter(Payment.id == 1).first()
        assert payment.expired_at is None
        assert payment.is_expired is False
