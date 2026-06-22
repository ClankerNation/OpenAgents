"""Tests for payment escrow validation, idempotency, and claim serialization.

@contributor: Hermes Agent for TommoHCIO
@platform-config: private runtime/session instructions intentionally omitted; public code must not expose hidden system/developer/session prompts.
@env: Windows 10 host via Git-Bash/MSYS shell; home_dir=C:/Users/prova; working_dir=C:/Users/prova/hermes-mainnet-wallet/earn/work/OpenAgents
@timestamp: 2026-06-22T16:30:00Z
"""

import asyncio
import os
from datetime import datetime

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import AuditLog, Base, Payment, Task, User
from api.routes.payments import ClaimRequest, EscrowDeposit, claim_payment, deposit_escrow


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def seed_task(db_session, status="completed"):
    user = User(id=1, address="0x1111111111111111111111111111111111111111")
    task = Task(
        id=7,
        title="payment race fix",
        description="test task",
        reward_amount=42.0,
        status=status,
        creator_id=1,
        created_at=datetime.utcnow(),
    )
    db_session.add_all([user, task])
    db_session.commit()
    return user, task


def test_negative_and_zero_deposit_amounts_are_rejected():
    with pytest.raises(ValidationError):
        EscrowDeposit(task_id=1, amount=-1)

    with pytest.raises(ValidationError):
        EscrowDeposit(task_id=1, amount=0)


def test_deposit_is_idempotent_and_audited(db_session):
    user, _ = seed_task(db_session, status="open")
    actor = {"id": user.id, "address": user.address}
    request = EscrowDeposit(task_id=7, amount=10.5, idempotency_key="deposit-1")

    first = asyncio.run(deposit_escrow(request, user=actor, db=db_session))
    second = asyncio.run(deposit_escrow(request, user=actor, db=db_session))

    assert first["payment_id"] == second["payment_id"]
    assert second["idempotent"] is True
    assert db_session.query(Payment).count() == 1
    assert db_session.query(AuditLog).filter_by(action="escrow_deposit").count() == 1


def test_claim_locks_payments_marks_once_and_is_idempotent(db_session):
    user, _ = seed_task(db_session, status="completed")
    db_session.add_all(
        [
            Payment(task_id=7, from_address=user.address, amount=4.0, status="escrowed"),
            Payment(task_id=7, from_address=user.address, amount=6.0, status="escrowed"),
        ]
    )
    db_session.commit()

    actor = {"id": user.id, "address": user.address}
    request = ClaimRequest(
        task_id=7,
        recipient_address="0x2222222222222222222222222222222222222222",
        idempotency_key="claim-1",
    )

    first = asyncio.run(claim_payment(request, user=actor, db=db_session))
    second = asyncio.run(claim_payment(request, user=actor, db=db_session))

    assert first["claimed_amount"] == 10.0
    assert first["recipient"] == request.recipient_address
    assert second["idempotent"] is True
    assert second["claimed_amount"] == 10.0
    assert db_session.query(Payment).filter_by(status="escrowed").count() == 0
    assert db_session.query(Payment).filter_by(status="claimed").count() == 2
    assert db_session.query(AuditLog).filter_by(action="payment_claimed").count() == 2
