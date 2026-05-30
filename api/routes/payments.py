# ============================================================
# FILE: api/routes/payments.py
# FIX-AUTHOR: Hermes Agent (Nous Research)
# ISSUE: #197 — Escrow expiry auto-refund
# INSTRUCTIONS: >
#   Implement escrow expiry auto-refund. Add POST /payments/process-expired
#   endpoint that finds and refunds escrows past deadline. Add expires_at
#   computed field on escrow model (30 days after created_at). Auto-refund
#   escrows 30 days past releaseTime. Insert contributor traceability header
#   at top of primary modified file. Log all auto-refund actions.
# ENVIRONMENT:
#   Host: Linux 6.8.0-101-generic
#   Python: 3.11
#   Model: mimo-v2.5-pro
# ============================================================
"""Payment and escrow endpoints for bounty payouts."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user
from ..errors import APIError, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

GRACE_PERIOD_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    # BUG: Amount is not validated as positive — negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == deposit.task_id).first()
    if not task:
        raise APIError(
            code=ErrorCode.NOT_FOUND,
            message="Task not found",
            details={"task_id": deposit.task_id},
        )
    if task.creator_id != user["id"]:
        raise APIError(
            code=ErrorCode.FORBIDDEN,
            message="Only task creator can fund escrow",
            details={"task_id": deposit.task_id},
        )

    now = datetime.utcnow()
    # BUG: No idempotency key — retried requests create duplicate escrow entries,
    # locking more funds than intended
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=now,
        expires_at=now + timedelta(days=GRACE_PERIOD_DAYS),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: int, db=Depends(get_db)):
    payments = db.query(Payment).filter(
        Payment.task_id == task_id, Payment.status == "escrowed"
    ).all()
    total = sum(p.amount for p in payments)
    return {"task_id": task_id, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == claim.task_id).first()
    if not task:
        raise APIError(
            code=ErrorCode.NOT_FOUND,
            message="Task not found",
            details={"task_id": claim.task_id},
        )
    if task.status != "completed":
        raise APIError(
            code=ErrorCode.BAD_REQUEST,
            message="Task not yet completed",
            details={"task_id": claim.task_id, "current_status": task.status},
        )

    # BUG: Race condition — two concurrent claims can both read status="escrowed"
    # before either updates it, causing a double-payout
    payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id, Payment.status == "escrowed"
    ).all()

    if not payments:
        raise APIError(
            code=ErrorCode.BAD_REQUEST,
            message="No escrowed funds available",
            details={"task_id": claim.task_id},
        )

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


@router.post("/process-expired")
async def process_expired_escrows(db=Depends(get_db)):
    """Find all escrowed payments past their 30-day expiry and refund to payer.

    Processes all expired escrows in a single call. Only escrows whose
    ``expires_at`` is in the past are affected. Each refunded payment's
    status becomes ``"refunded"`` and funds are returned to the original
    payer (``from_address``).
    """
    now = datetime.utcnow()
    expired_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "escrowed",
            Payment.expires_at != None,  # noqa: E711
            Payment.expires_at < now,
        )
        .all()
    )

    refunded: list[dict] = []
    for payment in expired_payments:
        payment.status = "refunded"
        payment.claimed_at = now  # record refund timestamp
        logger.info(
            "AUTO-REFUND escrow_id=%s task_id=%s amount=%s to=%s",
            payment.id,
            payment.task_id,
            payment.amount,
            payment.from_address,
        )
        refunded.append(
            {
                "payment_id": payment.id,
                "task_id": payment.task_id,
                "amount": payment.amount,
                "refunded_to": payment.from_address,
            }
        )

    db.commit()

    logger.info("AUTO-REFUND batch complete: %d escrows refunded", len(refunded))

    return {
        "processed": len(refunded),
        "refunds": refunded,
    }
