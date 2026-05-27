"""
Payment and escrow endpoints for bounty payouts.

@contributor tufstraka
@platform OpenClaw Gateway (amazon-bedrock/global.anthropic.claude-opus-4-5-20251101-v1:0)
@runtime Linux 6.17.0-1013-aws (arm64), /home/ubuntu/.openclaw/workspace
@date 2026-05-27T10:21:00Z
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


class EscrowDeposit(BaseModel):
    task_uuid: str
    # BUG: Amount is not validated as positive — negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_uuid: str
    recipient_address: str


def payment_to_response(payment: Payment) -> dict:
    """Convert Payment model to response dict with UUID as id."""
    return {
        "id": payment.uuid,
        "amount": payment.amount,
        "status": payment.status,
        "token_address": payment.token_address,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "claimed_at": payment.claimed_at.isoformat() if payment.claimed_at else None,
    }


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.uuid == deposit.task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # BUG: No idempotency key — retried requests create duplicate escrow entries,
    # locking more funds than intended
    payment = Payment(
        task_id=task.id,  # Internal ID for FK relationship
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.uuid, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_uuid}")
async def get_escrow_balance(task_uuid: str, db=Depends(get_db)):
    task = db.query(Task).filter(Task.uuid == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    payments = db.query(Payment).filter(
        Payment.task_id == task.id, Payment.status == "escrowed"
    ).all()
    total = sum(p.amount for p in payments)
    return {"task_uuid": task_uuid, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.uuid == claim.task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # BUG: Race condition — two concurrent claims can both read status="escrowed"
    # before either updates it, causing a double-payout
    payments = db.query(Payment).filter(
        Payment.task_id == task.id, Payment.status == "escrowed"
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
        "task_uuid": claim.task_uuid,
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
        "sent": [payment_to_response(p) for p in sent],
        "received": [payment_to_response(p) for p in received],
    }
