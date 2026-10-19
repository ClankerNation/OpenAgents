"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, SessionLocal, Payment, Task
from ..middleware.auth import get_current_user

logger = logging.getLogger("openagents.payments")
router = APIRouter(prefix="/payments", tags=["payments"])


class EscrowDeposit(BaseModel):
    task_id: int
    # BUG: Amount is not validated as positive — negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    release_time: Optional[datetime] = None


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
        release_time=deposit.release_time or (task.deadline if task and task.deadline else datetime.utcnow()),
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
async def process_expired_escrows(db=Depends(get_db)):
    """
    Finds and refunds all 'escrowed' payments past their 30-day grace period (now >= expired_at).
    Refund is transferred to the original payer (from_address) and logged with timestamp and escrow ID.
    """
    now = datetime.utcnow()
    escrowed_payments = db.query(Payment).filter(Payment.status == "escrowed").all()

    refunded_records = []
    for payment in escrowed_payments:
        expired_at = payment.expired_at
        if expired_at and now >= expired_at:
            payment.status = "refunded"
            payment.to_address = payment.from_address
            payment.claimed_at = now

            logger.info(
                f"[{now.isoformat()}] Auto-refunded expired escrow ID {payment.id} "
                f"for task {payment.task_id}: {payment.amount} returned to {payment.from_address}"
            )

            refunded_records.append({
                "payment_id": payment.id,
                "task_id": payment.task_id,
                "amount": payment.amount,
                "payer": payment.from_address,
                "refunded_at": now.isoformat(),
            })

    db.commit()
    return {
        "processed_count": len(refunded_records),
        "refunded_payments": refunded_records,
    }


def auto_refund_expired_escrows_job(db_session_factory=SessionLocal) -> int:
    """Background daemon job to find and auto-refund all expired escrows."""
    db = db_session_factory()
    try:
        now = datetime.utcnow()
        escrowed = db.query(Payment).filter(Payment.status == "escrowed").all()
        refunded = 0
        for p in escrowed:
            if p.expired_at and now >= p.expired_at:
                p.status = "refunded"
                p.to_address = p.from_address
                p.claimed_at = now
                logger.info(
                    f"[{now.isoformat()}] [Background Daemon] Auto-refunded expired escrow ID {p.id}: "
                    f"{p.amount} returned to {p.from_address}"
                )
                refunded += 1
        if refunded > 0:
            db.commit()
        return refunded
    finally:
        db.close()

