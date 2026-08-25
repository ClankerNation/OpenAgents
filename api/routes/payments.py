"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

# @fix-author rafaio1
# @date 2026-08-25T00:00:00Z
# @runtime linux x64 /tmp/openagents_issue_197 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

router = APIRouter(prefix="/payments", tags=["payments"])

# Escrow expiry configuration
ESCROW_EXPIRY_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float = Field(gt=0, description="Amount must be positive")
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    idempotency_key: str = Field(..., min_length=1, max_length=128, description="Unique key to prevent duplicate deposits")


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

    # Idempotency check: prevent duplicate deposits from retried requests
    existing = db.query(Payment).filter(
        Payment.task_id == deposit.task_id,
        Payment.from_address == user["address"],
        Payment.idempotency_key == deposit.idempotency_key
    ).first()
    
    if existing:
        return {"payment_id": existing.id, "status": existing.status, "amount": existing.amount, "duplicate": True}

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=ESCROW_EXPIRY_DAYS),
        idempotency_key=deposit.idempotency_key,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount, "expires_at": payment.expires_at.isoformat()}


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

    # Use SELECT FOR UPDATE to prevent race conditions on concurrent claims
    payments = db.query(Payment).with_for_update().filter(
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


@router.post("/refund-expired")
async def refund_expired_escrows(user=Depends(get_current_user), db=Depends(get_db)):
    """Auto-refund expired escrows back to the original depositor."""
    now = datetime.utcnow()
    expired_payments = db.query(Payment).with_for_update().filter(
        Payment.from_address == user["address"],
        Payment.status == "escrowed",
        Payment.expires_at <= now
    ).all()

    if not expired_payments:
        return {"refunded_count": 0, "total_refunded": 0.0}

    total_refunded = 0.0
    for payment in expired_payments:
        payment.status = "refunded"
        payment.refunded_at = now
        total_refunded += payment.amount

    db.commit()
    return {"refunded_count": len(expired_payments), "total_refunded": total_refunded}


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
