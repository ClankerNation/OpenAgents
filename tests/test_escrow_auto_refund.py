"""
Test escrow auto-refund endpoint (issue #197).
"""
import pytest
import sys
import os
from datetime import datetime, timedelta

# Add api dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Override DB for testing
os.environ["DATABASE_URL"] = "sqlite:///./test_openagents.db"
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")

from api.models.database import Base, get_db, Payment, Task, User, init_db
from api.routes.payments import router
from api.middleware.auth import create_access_token
from fastapi import FastAPI

# Create test app
app = FastAPI()
app.include_router(router)

# Test DB engine
TEST_DB_URL = "sqlite:///./test_escrow_refund.db"
test_engine = create_engine(TEST_DB_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables and seed minimal data before each test."""
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()

    # Create test user
    user = User(id=1, address="0xPayerAddress0000000000000000000000000001", username="testuser")
    db.add(user)
    db.commit()
    db.refresh(user)

    yield db

    # Cleanup
    Base.metadata.drop_all(bind=test_engine)
    db.close()


def _auth_header(user_id="1", address="0xPayerAddress0000000000000000000000000001"):
    """Generate a valid JWT for the test user."""
    from api.middleware.auth import create_access_token
    token = create_access_token({"sub": user_id, "address": address, "roles": []})
    return {"Authorization": f"Bearer {token}"}


def _create_escrow(db, payment_id=None, status="escrowed", release_offset_days=0,
                   created_offset_days=-60):
    """Helper: create a Payment record for testing."""
    now = datetime.utcnow()
    created_at = now + timedelta(days=created_offset_days)
    release_time = created_at + timedelta(days=30)
    # Adjust release time to test expiration: offset from now
    release_time = now + timedelta(days=release_offset_days)

    payment = Payment(
        id=payment_id or 1,
        task_id=100,
        from_address="0xPayerAddress0000000000000000000000000001",
        amount=1.0,
        status=status,
        created_at=created_at,
        release_time=release_time,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


class TestProcessExpiredEscrows:
    """Acceptance criteria for issue #197."""

    def test_fresh_escrow_not_affected(self, setup_db):
        """Fresh escrow (release_time in future) should NOT be refunded."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=+60)

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 0
        assert data["refunded"] == []

        # Verify escrow still intact
        payment = db.query(Payment).filter(Payment.id == 1).first()
        assert payment.status == "escrowed"
        assert payment.refunded_at is None

    def test_expired_escrow_refunded(self, setup_db):
        """Escrow past 30-day expiry window should be auto-refunded."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=-60)

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 1
        assert len(data["refunded"]) == 1
        assert data["refunded"][0]["payment_id"] == 1
        assert data["refunded"][0]["amount"] == 1.0
        assert data["refunded"][0]["from_address"] == "0xPayerAddress0000000000000000000000000001"

        # Verify status changed to refunded
        payment = db.query(Payment).filter(Payment.id == 1).first()
        assert payment.status == "refunded"
        assert payment.refunded_at is not None

    def test_multiple_expired_escrows_refunded(self, setup_db):
        """All expired escrows should be processed in one call."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=-60)
        _create_escrow(db, payment_id=2, release_offset_days=-90)
        _create_escrow(db, payment_id=3, release_offset_days=+30)  # not expired

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 2

        refunded_ids = {r["payment_id"] for r in data["refunded"]}
        assert refunded_ids == {1, 2}

        # Verify statuses
        assert db.query(Payment).filter(Payment.id == 1).first().status == "refunded"
        assert db.query(Payment).filter(Payment.id == 2).first().status == "refunded"
        assert db.query(Payment).filter(Payment.id == 3).first().status == "escrowed"

    def test_already_claimed_not_affected(self, setup_db):
        """Escrows already claimed should not be refunded."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=-60, status="claimed")

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 0

        payment = db.query(Payment).filter(Payment.id == 1).first()
        assert payment.status == "claimed"

    def test_no_release_time_skipped(self, setup_db):
        """Escrows without release_time should be skipped (legacy compatibility)."""
        db = setup_db
        now = datetime.utcnow()
        payment = Payment(
            id=99,
            task_id=100,
            from_address="0xPayerAddress0000000000000000000000000001",
            amount=2.0,
            status="escrowed",
            created_at=now - timedelta(days=365),
            release_time=None,
        )
        db.add(payment)
        db.commit()

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 0

    def test_requires_auth(self, setup_db):
        """Endpoint requires valid authentication."""
        response = client.post("/payments/process-expired")  # no auth header
        assert response.status_code in (401, 403)

    def test_refund_goes_to_payer(self, setup_db):
        """The refund should reference the original payer (from_address)."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=-60)

        response = client.post("/payments/process-expired", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["refunded"][0]["from_address"] == "0xPayerAddress0000000000000000000000000001"

    def test_idempotent(self, setup_db):
        """Calling process-expired twice should not double-refund."""
        db = setup_db
        _create_escrow(db, payment_id=1, release_offset_days=-60)

        # First call
        r1 = client.post("/payments/process-expired", headers=_auth_header())
        assert r1.json()["processed"] == 1

        # Second call — should find nothing new
        r2 = client.post("/payments/process-expired", headers=_auth_header())
        assert r2.json()["processed"] == 0
