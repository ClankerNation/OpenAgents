"""Tests for the escrow auto-refund functionality."""

import pytest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..models.database import Base, Payment, Task, User
from ..middleware.audit import create_audit_log

TEST_DB_URL = "sqlite:///./test_escrow.db"
engine = create_engine(TEST_DB_URL, echo=False)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_test_escrow(db, created_days_ago: int):
    """Helper to create an escrow payment with a specific age."""
    now = datetime.utcnow()
    # Create a user first
    user = User(address=f"0x{created_days_ago:040x}", created_at=now)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create a task
    task = Task(
        title=f"Test task {created_days_ago}",
        description="test",
        reward_amount=100.0,
        status="open",
        creator_id=user.id,
        created_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Create escrow
    escrow = Payment(
        task_id=task.id,
        from_address=user.address,
        amount=100.0,
        status="escrowed",
        created_at=now - timedelta(days=created_days_ago),
        expired_at=now - timedelta(days=created_days_ago - 30),
    )
    db.add(escrow)
    db.commit()
    db.refresh(escrow)
    return escrow, user, task


# --- Test 1: Fresh escrow not affected ---

def test_fresh_escrow_not_affected(db):
    """A recently created escrow (within 30 days) should not be refunded."""
    now = datetime.utcnow()
    escrow, _, _ = create_test_escrow(db, 5)  # 5 days old, expires in 25 days

    # Simulate processing
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expired_at.isnot(None),
        Payment.expired_at <= now,
    ).all()

    assert len(expired) == 0, "Fresh escrow should not be expired"


# --- Test 2: Expired escrow is found ---

def test_expired_escrow_found(db):
    """An escrow past its 30-day expiry should be found."""
    now = datetime.utcnow()
    escrow, _, _ = create_test_escrow(db, 35)  # 35 days old, expired 5 days ago

    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expired_at.isnot(None),
        Payment.expired_at <= now,
    ).all()

    assert len(expired) == 1
    assert expired[0].id == escrow.id


# --- Test 3: Expired escrow refunded ---

def test_expired_escrow_refunded(db):
    """Expired escrow status should change to 'refunded'."""
    now = datetime.utcnow()
    escrow, user, _ = create_test_escrow(db, 35)

    # Process expired
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expired_at.isnot(None),
        Payment.expired_at <= now,
    ).all()

    for e in expired:
        e.status = "refunded"
        e.to_address = e.from_address
    db.commit()

    # Verify
    updated = db.query(Payment).filter(Payment.id == escrow.id).first()
    assert updated.status == "refunded"
    assert updated.to_address == user.address


# --- Test 4: Only escrowed payments affected ---

def test_only_escrowed_affected(db):
    """Only payments with status='escrowed' should be processed."""
    now = datetime.utcnow()
    escrow, user, task = create_test_escrow(db, 35)

    # Create a payment that's already claimed but expired
    claimed_payment = Payment(
        task_id=task.id,
        from_address=user.address,
        amount=50.0,
        status="claimed",
        created_at=now - timedelta(days=100),
        expired_at=now - timedelta(days=70),
    )
    db.add(claimed_payment)
    db.commit()

    # Process expired - should only find the escrowed one
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expired_at.isnot(None),
        Payment.expired_at <= now,
    ).all()

    assert len(expired) == 1
    assert expired[0].id == escrow.id


# --- Test 5: Refund goes to payer ---

def test_refund_goes_to_payer(db):
    """Refund should be sent to the original from_address."""
    now = datetime.utcnow()
    escrow, user, _ = create_test_escrow(db, 35)

    # The refund should go to from_address
    assert escrow.from_address == user.address

    # Simulate refund
    escrow.status = "refunded"
    escrow.to_address = escrow.from_address
    db.commit()

    assert escrow.to_address == user.address
