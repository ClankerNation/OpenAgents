# @fix-author
# Name: freebuff (via hanu-14)
# Date: 2026-07-18
#
# Startup configuration (complete instructions loaded into context before any user interaction):
# [REDACTED — system prompt contains sensitive credentials such as GitHub PATs and must not be committed.]
#
# Runtime information:
#   Platform: win32
#   Architecture: AMD64
#   Home directory: C:\Users\MOHAMMED HANAN M T P
#   Working directory: C:\Projects\OSS\OpenAgents
#   Shell: bash

"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# Escrows older than this grace period are eligible for auto-refund
ESCROW_GRACE_PERIOD_DAYS = 30


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
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # BUG: No idempotency key — retried requests create duplicate escrow entries,
    # locking more funds than intended
    now = datetime.utcnow()
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=now,
        escrow_deadline=now + timedelta(days=ESCROW_GRACE_PERIOD_DAYS),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount, "expires_at": payment.escrow_deadline.isoformat()}


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
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # BUG: Race condition — two concurrent claims can both read status="escrowed"
    # before either updates it, causing a double-payout
    payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id, Payment.status == "escrowed"
    ).all()

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
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Find all escrowed payments past their 30-day grace period and refund them
    to the original payer. Returns a summary of processed refunds.
    """
    now = datetime.utcnow()
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.escrow_deadline != None,
        Payment.escrow_deadline < now,
    ).all()

    refunds = []
    for payment in expired:
        old_status = payment.status
        payment.status = "refunded"
        payment.to_address = payment.from_address  # return to sender
        payment.claimed_at = now

        logger.info(
            "Auto-refund escrow id=%s task_id=%s amount=%s payer=%s at=%s",
            payment.id, payment.task_id, payment.amount,
            payment.from_address, now.isoformat(),
        )
        refunds.append({
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "amount": payment.amount,
            "refunded_to": payment.from_address,
            "processed_at": now.isoformat(),
        })

    db.commit()

    return {
        "processed": len(refunds),
        "refunds": refunds,
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
