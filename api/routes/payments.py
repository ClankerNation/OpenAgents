"""
Contributor Metadata (required for bounty #197)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
"""

"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

EXPIRY_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    # BUG: Amount is not validated as positive � negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


class ProcessExpiredResponse(BaseModel):
    processed: int
    refunded: list
    total_refunded: float


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    if deposit.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    task = db.query(Task).filter(Task.id == deposit.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # BUG: No idempotency key � retried requests create duplicate escrow entries,
    # locking more funds than intended
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=EXPIRY_DAYS),
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
    now = datetime.utcnow()
    expired = [p for p in payments if p.expires_at and p.expires_at < now]
    return {
        "task_id": task_id,
        "escrowed_total": total,
        "deposits": len(payments),
        "expired_count": len(expired),
    }


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == claim.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # BUG: Race condition � two concurrent claims can both read status="escrowed"
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
    """Find and refund escrows past their expiry deadline."""
    now = datetime.utcnow()
    expired_payments = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expires_at.isnot(None),
        Payment.expires_at < now,
    ).all()

    refunded = []
    total_refunded = 0.0

    for payment in expired_payments:
        payment.status = "refunded"
        payment.refunded_at = now
        refunded.append({
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "amount": payment.amount,
            "from_address": payment.from_address,
        })
        total_refunded += payment.amount

    db.commit()

    return {
        "processed": len(expired_payments),
        "refunded": refunded,
        "total_refunded": total_refunded,
    }
