import asyncio
import os

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import Base, Payment, PaymentAuditLog, Task, User
from api.routes.payments import EscrowDeposit, ClaimRequest, claim_payment, deposit_escrow


def make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_task(db, status="completed"):
    user = User(address="0x1111111111111111111111111111111111111111", username="creator")
    db.add(user)
    db.flush()
    task = Task(
        title="task",
        reward_amount=10.0,
        status=status,
        creator_id=user.id,
    )
    db.add(task)
    db.commit()
    return user, task


def test_deposit_rejects_non_positive_amount():
    try:
        EscrowDeposit(task_id=1, amount=-1)
    except ValidationError as error:
        assert "greater than 0" in str(error)
    else:
        raise AssertionError("negative escrow deposit was accepted")


def test_deposit_idempotency_key_reuses_existing_payment():
    db = make_session()
    user, task = seed_task(db)
    current_user = {"id": user.id, "address": user.address}
    deposit = EscrowDeposit(task_id=task.id, amount=10.0, idempotency_key="retry-1")

    first = asyncio.run(deposit_escrow(deposit, user=current_user, db=db))
    second = asyncio.run(deposit_escrow(deposit, user=current_user, db=db))

    assert first == second
    assert db.query(Payment).count() == 1
    assert db.query(PaymentAuditLog).filter_by(action="escrow_deposit").count() == 1


def test_claim_serializes_payments_and_blocks_double_claim():
    db = make_session()
    user, task = seed_task(db)
    payment = Payment(
        task_id=task.id,
        from_address=user.address,
        amount=10.0,
        status="escrowed",
    )
    db.add(payment)
    db.commit()

    current_user = {"id": user.id, "address": user.address}
    first = asyncio.run(claim_payment(
        ClaimRequest(task_id=task.id, recipient_address=user.address),
        user=current_user,
        db=db,
    ))

    assert first["claimed_amount"] == 10.0
    assert db.query(Payment).first().status == "claimed"
    assert db.query(PaymentAuditLog).filter_by(action="payment_claimed").count() == 1

    try:
        asyncio.run(claim_payment(
            ClaimRequest(task_id=task.id, recipient_address=user.address),
            user=current_user,
            db=db,
        ))
    except HTTPException as error:
        assert error.status_code == 400
        assert error.detail == "No escrowed funds available"
    else:
        raise AssertionError("second claim unexpectedly succeeded")
