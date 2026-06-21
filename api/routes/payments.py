"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

logger = logging.getLogger(__name__)

# Grace period after releaseTime before auto-refund triggers
ESCROW_GRACE_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    idempotency_key: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Deposit amount must be positive")
        return v


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


def _compute_expired_at(payment_created_at: datetime) -> datetime:
    """Compute when an escrow becomes eligible for auto-refund.

    Escrows expire 30 days after creation if no release has occurred.
    """
    created = payment_created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created + timedelta(days=ESCROW_GRACE_DAYS)


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == deposit.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # Idempotency: if key provided, check for existing deposit
    if deposit.idempotency_key:
        existing = (
            db.query(Payment)
            .filter(Payment.idempotency_key == deposit.idempotency_key)
            .first()
        )
        if existing:
            return {
                "payment_id": existing.id,
                "status": existing.status,
                "amount": existing.amount,
            }

    now = datetime.utcnow()
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=now,
        expired_at=_compute_expired_at(now),
        idempotency_key=deposit.idempotency_key,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: int, db=Depends(get_db)):
    payments = (
        db.query(Payment)
        .filter(Payment.task_id == task_id, Payment.status == "escrowed")
        .all()
    )
    total = sum(p.amount for p in payments)
    return {"task_id": task_id, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == claim.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # Use SELECT ... FOR UPDATE to prevent race condition / double-payout
    payments = (
        db.query(Payment)
        .filter(Payment.task_id == claim.task_id, Payment.status == "escrowed")
        .with_for_update()
        .all()
    )

    if not payments:
        raise HTTPException(status_code=400, detail="No escrowed funds available")

    total_claimed = 0.0
    for payment in payments:
        payment.status = "claimed"
        payment.to_address = claim.recipient_address
        payment.claimed_at = datetime.utcnow()
        total_claimed += payment.amount

    db.commit()
    return {
        "task_id": claim.task_id,
        "claimed_amount": total_claimed,
        "recipient": claim.recipient_address,
    }


@router.post("/process-expired")
async def process_expired_escrows(
    user=Depends(get_current_user), db=Depends(get_db)
):
    """Find and refund escrows past the 30-day grace period.

    Only processes escrows whose expired_at timestamp has passed.
    Refunds go back to the original payer (from_address).
    """
    now = datetime.utcnow()

    expired_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "escrowed",
            Payment.expired_at != None,
            Payment.expired_at <= now,
        )
        .all()
    )

    if not expired_payments:
        return {"processed": 0, "message": "No expired escrows found"}

    refund_count = 0
    total_refunded = 0.0

    for payment in expired_payments:
        original_amount = payment.amount
        original_payer = payment.from_address

        payment.status = "refunded"
        payment.to_address = original_payer
        payment.claimed_at = now  # reuse claimed_at as refunded_at

        refund_count += 1
        total_refunded += original_amount

        logger.info(
            "Auto-refunded escrow %d: $%.2f -> %s (expired_at: %s)",
            payment.id,
            original_amount,
            original_payer,
            payment.expired_at.isoformat() if payment.expired_at else "N/A",
        )

    db.commit()

    return {
        "processed": refund_count,
        "total_refunded": total_refunded,
        "message": f"Refunded {refund_count} expired escrows totaling ${total_refunded:.2f}",
    }


@router.get("/history")
async def payment_history(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sent = db.query(Payment).filter(Payment.from_address == user["address"]).all()
    received = db.query(Payment).filter(Payment.to_address == user["address"]).all()
    return {
        "sent": [{"id": p.id, "amount": p.amount, "status": p.status} for p in sent],
        "received": [{"id": p.id, "amount": p.amount, "status": p.status} for p in received],
    }
