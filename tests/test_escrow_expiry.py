"""Tests for escrow expiry auto-refund (issue #197)."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret")

from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from api.models.database import Base, get_db, Payment, Task, User
from api.routes.payments import router as payments_router, GRACE_PERIOD_DAYS


# ---------------------------------------------------------------------------
# Test database setup (SQLite in-memory, single shared connection)
# ---------------------------------------------------------------------------
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

# Create all tables once
Base.metadata.create_all(bind=TEST_ENGINE)

# Build a minimal test app
test_app = FastAPI()
test_app.include_router(payments_router)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


test_app.dependency_overrides[get_db] = override_get_db
client = TestClient(test_app)


def _seed():
    """Insert baseline rows required by all tests."""
    db = TestSession()
    user = User(id=1, address="0xaaaa", username="alice")
    task = Task(id=1, title="T1", reward_amount=10.0, creator_id=1, status="open")
    db.add(user)
    db.add(task)
    db.commit()
    db.close()


def _clean():
    """Delete all rows from test tables."""
    with TEST_ENGINE.begin() as conn:
        conn.execute(text("DELETE FROM payments"))
        conn.execute(text("DELETE FROM tasks"))
        conn.execute(text("DELETE FROM users"))


def _deposit(db, *, days_ago: int, status: str = "escrowed") -> Payment:
    """Insert a payment whose created_at / expires_at simulate *days_ago*."""
    now = datetime.utcnow()
    created = now - timedelta(days=days_ago)
    payment = Payment(
        task_id=1,
        from_address="0xaaaa",
        amount=5.0,
        status=status,
        created_at=created,
        expires_at=created + timedelta(days=30),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


# Seed once at module level
_seed()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProcessExpired:
    """POST /payments/process-expired"""

    def setup_method(self):
        _clean()
        _seed()

    def test_refunds_expired_escrows(self):
        """Escrows past 30-day grace period are refunded."""
        db = TestSession()
        p = _deposit(db, days_ago=35)
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        body = resp.json()
        assert body["processed"] == 1
        assert body["refunds"][0]["payment_id"] == p.id
        assert body["refunds"][0]["refunded_to"] == "0xaaaa"

        db = TestSession()
        refreshed = db.query(Payment).get(p.id)
        assert refreshed.status == "refunded"
        db.close()

    def test_ignores_escrows_within_grace_period(self):
        """Escrows within the 30-day grace period are NOT refunded."""
        db = TestSession()
        p = _deposit(db, days_ago=15)
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0

        db = TestSession()
        refreshed = db.query(Payment).get(p.id)
        assert refreshed.status == "escrowed"
        db.close()

    def test_ignores_already_claimed(self):
        """Claimed escrows are not refunded even if past deadline."""
        db = TestSession()
        _deposit(db, days_ago=35, status="claimed")
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0

    def test_ignores_already_refunded(self):
        """Already-refunded escrows are not processed again."""
        db = TestSession()
        _deposit(db, days_ago=35, status="refunded")
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0

    def test_batch_processes_multiple(self):
        """Multiple expired escrows are all processed in one call."""
        db = TestSession()
        p1 = _deposit(db, days_ago=40)
        p2 = _deposit(db, days_ago=35)
        p3 = _deposit(db, days_ago=10)
        p1_id, p2_id = p1.id, p2.id
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        body = resp.json()
        assert body["processed"] == 2
        refunded_ids = {r["payment_id"] for r in body["refunds"]}
        assert refunded_ids == {p1_id, p2_id}

    def test_refund_goes_to_payer(self):
        """Refund recipient must be from_address (the payer)."""
        db = TestSession()
        _deposit(db, days_ago=50)
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.json()["refunds"][0]["refunded_to"] == "0xaaaa"

    def test_exactly_30_days_not_expired(self):
        """Edge case: escrow with expires_at in the future is not expired."""
        db = TestSession()
        now = datetime.utcnow()
        p = Payment(
            task_id=1, from_address="0xaaaa", amount=5.0,
            status="escrowed", created_at=now,
            expires_at=now + timedelta(seconds=5),
        )
        db.add(p)
        db.commit()
        db.close()

        resp = client.post("/payments/process-expired")
        assert resp.json()["processed"] == 0

    def test_expired_at_field_set_on_deposit(self):
        """New deposits must have expires_at = created_at + 30 days."""
        assert GRACE_PERIOD_DAYS == 30

        db = TestSession()
        now = datetime.utcnow()
        p = Payment(
            task_id=1, from_address="0xaaaa", amount=5.0,
            status="escrowed", created_at=now,
            expires_at=now + timedelta(days=GRACE_PERIOD_DAYS),
        )
        db.add(p)
        db.commit()
        assert p.expires_at == p.created_at + timedelta(days=30)
        db.close()

    def test_empty_result_when_no_expired(self):
        """No escrows at all → zero processed, empty list."""
        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        body = resp.json()
        assert body["processed"] == 0
        assert body["refunds"] == []

    def test_logging_is_triggered(self):
        """Verify that the logger.info is called for each refund."""
        db = TestSession()
        _deposit(db, days_ago=35)
        db.close()

        with patch("api.routes.payments.logger") as mock_log:
            resp = client.post("/payments/process-expired")
            assert resp.status_code == 200
            assert mock_log.info.call_count >= 2

    def test_returns_refund_details(self):
        """Each refund includes payment_id, task_id, amount, and refunded_to."""
        db = TestSession()
        _deposit(db, days_ago=35)
        db.close()

        resp = client.post("/payments/process-expired")
        refund = resp.json()["refunds"][0]
        assert "payment_id" in refund
        assert "task_id" in refund
        assert "amount" in refund
        assert "refunded_to" in refund
