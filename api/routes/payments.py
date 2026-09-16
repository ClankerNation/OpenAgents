"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

ESCROW_GRACE_PERIOD_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
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

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
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

    payment = db.query(Payment).filter(
        Payment.task_id == claim.task_id, Payment.status == "escrowed"
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="No escrow found for this task")

    payment.status = "claimed"
    payment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "claimed", "amount": payment.amount}


@router.post("/process-expired")
async def process_expired_escrows(user=Depends(get_current_user), db=Depends(get_db)):
    """Find and refund escrows that are past the 30-day grace period after releaseTime.

    Only escrows where the task's release_time + 30 days < now are affected.
    Each refund is logged with timestamp and escrow ID.
    """
    now = datetime.utcnow()
    grace_period = timedelta(days=ESCROW_GRACE_PERIOD_DAYS)

    # Find all escrowed payments whose task has a release_time
    escrowed_payments = db.query(Payment).filter(
        Payment.status == "escrowed"
    ).all()

    refunded = []
    for payment in escrowed_payments:
        task = db.query(Task).filter(Task.id == payment.task_id).first()
        if not task or not task.release_time:
            continue

        expired_at = task.release_time + grace_period
        if now > expired_at:
            # Auto-refund: mark as refunded to payer
            payment.status = "refunded"
            payment.updated_at = now
            db.commit()
            db.refresh(payment)

            log_entry = {
                "timestamp": now.isoformat(),
                "escrow_id": payment.id,
                "task_id": payment.task_id,
                "payer_address": payment.from_address,
                "amount": payment.amount,
                "token_address": payment.token_address,
                "expired_at": expired_at.isoformat(),
                "action": "auto_refund",
            }
            logger.info(f"Auto-refund: {log_entry}")
            refunded.append(log_entry)

    return {
        "processed": len(refunded),
        "refunds": refunded,
        "timestamp": now.isoformat(),
    }
