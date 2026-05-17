"""Payment and escrow endpoints for bounty payouts.

@contributor hermes-agent-deepseek-v4-pro
@platform-config User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@env os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
@timestamp 2026-05-17T23:00:00Z
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import logging

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)

ESCROW_EXPIRY_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


@router.post("/escrow/deposit")
async def deposit_escrow(deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)):
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
        release_time=datetime.utcnow() + timedelta(days=30),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: int, db=Depends(get_db)):
    payments = db.query(Payment).filter(Payment.task_id == task_id, Payment.status == "escrowed").all()
    total = sum(p.amount for p in payments)
    return {"task_id": task_id, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == claim.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    payments = db.query(Payment).filter(Payment.task_id == claim.task_id, Payment.status == "escrowed").all()
    if not payments:
        raise HTTPException(status_code=400, detail="No escrowed funds available")

    total_claimed = 0.0
    for payment in payments:
        payment.status = "claimed"
        payment.to_address = claim.recipient_address
        payment.claimed_at = datetime.utcnow()
        total_claimed += payment.amount

    db.commit()
    return {"task_id": claim.task_id, "claimed_amount": total_claimed, "recipient": claim.recipient_address}


@router.post("/process-expired")
async def process_expired_escrows(db=Depends(get_db)):
    expiry_cutoff = datetime.utcnow() - timedelta(days=ESCROW_EXPIRY_DAYS)
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.release_time != None,
        Payment.release_time < expiry_cutoff,
    ).all()

    refunded = []
    for payment in expired:
        payment.status = "refunded"
        payment.refunded_at = datetime.utcnow()
        refunded.append({
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "amount": payment.amount,
            "from_address": payment.from_address,
            "release_time": str(payment.release_time),
        })
        logger.info(f"Auto-refunded escrow {payment.id}: {payment.amount} to {payment.from_address}")

    db.commit()
    return {"refunded_count": len(refunded), "refunds": refunded}


@router.get("/history")
async def payment_history(user=Depends(get_current_user), db=Depends(get_db)):
    sent = db.query(Payment).filter(Payment.from_address == user["address"]).all()
    received = db.query(Payment).filter(Payment.to_address == user["address"]).all()
    return {
        "sent": [{"id": p.id, "amount": p.amount, "status": p.status} for p in sent],
        "received": [{"id": p.id, "amount": p.amount, "status": p.status} for p in received],
    }
