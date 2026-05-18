"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18

Tests for escrow auto-refund on expired payments (bounty #197).
"""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest")

import pytest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from api.models.database import Base, Payment, Task, User, get_db
from api.main import app
from api.middleware.auth import get_current_user


# ── SQLite file-based DB for tests ────────────────────────────────────────
TEST_DB_PATH = "/tmp/test_openagents_escrow.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Override auth — every request is "authenticated" as user id=1
FAKE_USER = {"id": 1, "address": "0xabcdef1234567890abcdef1234567890abcdef12", "roles": ["user"]}


async def fake_get_current_user():
    return FAKE_USER


app.dependency_overrides[get_current_user] = fake_get_current_user

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a fresh DB session per test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_task_and_user(db):
    """Seed a user + task so foreign-key constraints pass."""
    user = User(id=1, address="0xabcdef1234567890abcdef1234567890abcdef12")
    db.add(user)
    db.commit()
    task = Task(
        id=1,
        title="Test task",
        description="desc",
        reward_amount=100.0,
        status="open",
        creator_id=1,
    )
    db.add(task)
    db.commit()
    return task


def _make_payment(db, task_id=1, days_ago=0, status="escrowed",
                  release_time=None, from_address="0xabcdef1234567890abcdef1234567890abcdef12"):
    """Helper to create a Payment row."""
    created = datetime.utcnow() - timedelta(days=days_ago)
    p = Payment(
        task_id=task_id,
        from_address=from_address,
        amount=50.0,
        status=status,
        created_at=created,
        release_time=release_time,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ── Tests: Payment.expired_at property ───────────────────────────────────

class TestExpiredAtProperty:
    """Test the expired_at computed field on the Payment model."""

    def test_expired_at_with_release_time(self, db_session):
        _seed_task_and_user(db_session)
        release = datetime.utcnow() - timedelta(days=35)
        p = _make_payment(db_session, days_ago=40, release_time=release)
        expected = release + timedelta(days=30)
        assert p.expired_at == expected

    def test_expired_at_without_release_time(self, db_session):
        _seed_task_and_user(db_session)
        p = _make_payment(db_session, days_ago=40, release_time=None)
        expected = p.created_at + timedelta(days=30)
        assert p.expired_at == expected

    def test_expired_at_is_30_days_past_release_time(self, db_session):
        _seed_task_and_user(db_session)
        release = datetime(2026, 1, 1, 0, 0, 0)
        p = _make_payment(db_session, days_ago=60, release_time=release)
        assert p.expired_at == datetime(2026, 1, 31, 0, 0, 0)


# ── Tests: POST /payments/process-expired ────────────────────────────────

class TestProcessExpiredEscrows:
    """Test the process-expired endpoint."""

    def test_no_expired_escrows(self, db_session):
        """When all escrows are fresh, nothing is refunded."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=5, status="escrowed")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 0
        assert data["refunded"] == []

    def test_expired_escrow_is_refunded(self, db_session):
        """An escrow 31 days past created_at should be auto-refunded."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=31, status="escrowed")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 1

        refund = data["refunded"][0]
        assert refund["task_id"] == 1
        assert refund["amount"] == 50.0
        assert "expired_at" in refund
        assert "refunded_at" in refund

    def test_expired_escrow_with_release_time(self, db_session):
        """Escrows 30 days past the release_time should be refunded."""
        _seed_task_and_user(db_session)
        release = datetime.utcnow() - timedelta(days=31)
        _make_payment(db_session, days_ago=40, release_time=release, status="escrowed")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 1

    def test_not_yet_expired_is_not_refunded(self, db_session):
        """An escrow that is only 29 days past should NOT be refunded."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=29, status="escrowed")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 0

    def test_already_claimed_not_refunded(self, db_session):
        """Payments with status 'claimed' should not be refunded."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=60, status="claimed")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 0

    def test_already_refunded_not_double_refunded(self, db_session):
        """Payments already refunded should not be processed again."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=60, status="refunded")

        resp = client.post("/payments/process-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refunded_count"] == 0

    def test_multiple_expired_escrows(self, db_session):
        """Multiple expired escrows should all be refunded in one call."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=31, status="escrowed", from_address="0xabcdef1234567890abcdef1234567890abcdef12")
        _make_payment(db_session, days_ago=45, status="escrowed", from_address="0x1111111111111111111111111111111111111111")
        _make_payment(db_session, days_ago=5, status="escrowed", from_address="0x2222222222222222222222222222222222222222")

        resp = client.post("/payments/process-expired")
        data = resp.json()
        assert data["refunded_count"] == 2  # only the two expired ones

    def test_db_status_updated_to_refunded(self, db_session):
        """After processing, the Payment rows should have status='refunded' and refunded_at set."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=35, status="escrowed")

        client.post("/payments/process-expired")

        payment = db_session.query(Payment).filter(Payment.status == "refunded").first()
        assert payment is not None
        assert payment.refunded_at is not None

    def test_process_expired_idempotent(self, db_session):
        """Calling process-expired twice should not refund the same payment twice."""
        _seed_task_and_user(db_session)
        _make_payment(db_session, days_ago=40, status="escrowed")

        resp1 = client.post("/payments/process-expired")
        assert resp1.json()["refunded_count"] == 1

        resp2 = client.post("/payments/process-expired")
        assert resp2.json()["refunded_count"] == 0