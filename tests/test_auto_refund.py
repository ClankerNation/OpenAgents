import os
import sys
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Ensure api is importable and test environment variables are set
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from api.models.database import Base, User, Task, Payment, get_db
from api.routes.payments import router as payments_router, auto_refund_expired_escrows_job
from fastapi import FastAPI

# In-memory test database with StaticPool so all connections share the schema
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

app = FastAPI()
app.include_router(payments_router)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    # Seed test user and task
    user = User(id=1, address="0x1111111111111111111111111111111111111111", username="creator")
    task = Task(id=1, title="Test Task", reward_amount=100.0, creator_id=1, status="open")
    db.add(user)
    db.add(task)
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)


def test_expired_at_property():
    """Verify expired_at computed property calculates 30 days past releaseTime."""
    db = TestingSessionLocal()
    now = datetime.utcnow()
    release_t = now - timedelta(days=10)

    payment = Payment(
        task_id=1,
        from_address="0x1111111111111111111111111111111111111111",
        amount=50.0,
        status="escrowed",
        created_at=now,
        release_time=release_t,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    assert payment.releaseTime == release_t
    assert payment.expired_at == release_t + timedelta(days=30)
    db.close()


def test_fresh_escrow_not_refunded():
    """Ensure escrows within the 30-day grace period are not refunded."""
    db = TestingSessionLocal()
    now = datetime.utcnow()

    # Escrow released 10 days ago (only 10 days into 30 day grace period)
    fresh_payment = Payment(
        task_id=1,
        from_address="0x1111111111111111111111111111111111111111",
        amount=75.0,
        status="escrowed",
        created_at=now - timedelta(days=10),
        release_time=now - timedelta(days=10),
    )
    db.add(fresh_payment)
    db.commit()
    db.refresh(fresh_payment)
    fresh_id = fresh_payment.id
    db.close()

    response = client.post("/payments/process-expired")
    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 0

    db = TestingSessionLocal()
    re_check = db.query(Payment).filter(Payment.id == fresh_id).first()
    assert re_check.status == "escrowed"
    assert re_check.to_address is None
    db.close()


def test_expired_escrow_is_refunded():
    """Ensure escrows past the 30-day grace period are auto-refunded to payer."""
    db = TestingSessionLocal()
    now = datetime.utcnow()
    payer_addr = "0x1111111111111111111111111111111111111111"

    # Escrow released 35 days ago (past 30-day grace period)
    expired_payment = Payment(
        task_id=1,
        from_address=payer_addr,
        amount=150.0,
        status="escrowed",
        created_at=now - timedelta(days=40),
        release_time=now - timedelta(days=35),
    )
    db.add(expired_payment)
    db.commit()
    db.refresh(expired_payment)
    expired_id = expired_payment.id
    db.close()

    response = client.post("/payments/process-expired")
    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 1
    assert data["refunded_payments"][0]["payment_id"] == expired_id
    assert data["refunded_payments"][0]["payer"] == payer_addr
    assert data["refunded_payments"][0]["amount"] == 150.0

    db = TestingSessionLocal()
    re_check = db.query(Payment).filter(Payment.id == expired_id).first()
    assert re_check.status == "refunded"
    assert re_check.to_address == payer_addr
    assert re_check.claimed_at is not None
    db.close()


def test_background_daemon_job():
    """Verify auto_refund_expired_escrows_job callable by background daemon."""
    db = TestingSessionLocal()
    now = datetime.utcnow()
    payer = "0x1111111111111111111111111111111111111111"

    # 1 expired, 1 fresh
    p_expired = Payment(
        task_id=1,
        from_address=payer,
        amount=200.0,
        status="escrowed",
        created_at=now - timedelta(days=50),
        release_time=now - timedelta(days=40),
    )
    p_fresh = Payment(
        task_id=1,
        from_address=payer,
        amount=100.0,
        status="escrowed",
        created_at=now - timedelta(days=5),
        release_time=now - timedelta(days=5),
    )
    db.add(p_expired)
    db.add(p_fresh)
    db.commit()
    db.close()

    refunded_count = auto_refund_expired_escrows_job(db_session_factory=TestingSessionLocal)
    assert refunded_count == 1

    db = TestingSessionLocal()
    p1 = db.query(Payment).filter(Payment.amount == 200.0).first()
    p2 = db.query(Payment).filter(Payment.amount == 100.0).first()
    assert p1.status == "refunded"
    assert p1.to_address == payer
    assert p2.status == "escrowed"
    db.close()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
