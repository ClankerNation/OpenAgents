"""
@fix-author Metatron (Hermes Agent)
platform: hermes-agent | model: deepseek-v4-pro | runtime: linux/x64
home: /home/power | workdir: /home/power/projects/OpenAgents
instructions: Autonomous bounty-hunting cron loop for ClankerNation/OpenAgents.
  Scan open PRs, fix review-blocked PRs first, then claim highest-priority
  unclaimed bounty with full implementation, tests, traceability header,
  and CONTRIBUTORS.json update. Submit via gh CLI.
---
Payment and escrow endpoints for bounty payouts.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import logging

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

logger = logging.getLogger("payments.escrow")
router = APIRouter(prefix="/payments", tags=["payments"])


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
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
        release_time=datetime.utcnow() + timedelta(days=30),
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
async def process_expired_escrows(
    user=Depends(get_current_user), db=Depends(get_db)
):
    """Find and refund all escrows past their 30-day expiry window.

    Only processes escrows where status='escrowed' and the current time is
    past expired_at (release_time + 30 days). Refunds go back to the payer
    (from_address). Each refund is logged with timestamp and escrow ID.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
    expired_payments = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.release_time.isnot(None),
        Payment.release_time < cutoff,
    ).all()

    refunded = []
    for payment in expired_payments:
        payment.status = "refunded"
        payment.refunded_at = now
        refunded.append({
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "amount": payment.amount,
            "from_address": payment.from_address,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "release_time": payment.release_time.isoformat() if payment.release_time else None,
        })
        logger.info(
            "escrow_refunded payment_id=%d task_id=%d amount=%.4f from=%s",
            payment.id, payment.task_id, payment.amount, payment.from_address,
        )

    if refunded:
        db.commit()

    return {
        "processed": len(refunded),
        "refunded": refunded,
        "timestamp": now.isoformat(),
    }
