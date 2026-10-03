# CONTRIBUTOR TRACEABILITY HEADER
# Agent: Atlas (Sovereign Bounty Fleet)
# Platform Instructions: [Bounty $2k] [ API ] Fix payments.py escrow release has no expiry auto-refund job — mainnet prep
# Session Start: 2026-10-03T17:30:00Z
# Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-a7a97678c9d7
# Platform: GitHub (ClankerNation/OpenAgents)
# Issue: #197 — [ Bounty $2k ] [ API ] Fix payments.py escrow release has no expiry auto-refund job — mainnet prep

"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


class ProcessExpiredResponse(BaseModel):
    processed: int
    refunded: int
    total_refunded: float
    details: List[dict]


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    task = db.query(Task).filter(Task.id == deposit.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")
    if deposit.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")

    # Idempotency: prevent duplicate deposits for same task by same user
    existing = db.query(Payment).filter(
        Payment.task_id == deposit.task_id,
        Payment.from_address == user["address"],
        Payment.status == "escrowed",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Escrow already exists for this task by this user")

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
        release_time=datetime.utcnow(),
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

    # Race condition fix: use row-level locking with FOR UPDATE
    payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id,
        Payment.status == "escrowed",
    ).with_for_update().all()

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


@router.post("/process-expired", response_model=ProcessExpiredResponse)
async def process_expired_escrows(
    user=Depends(get_current_user), db=Depends(get_db)
):
    """
    Process all expired escrows: refund to payer, log each action.
    Only escrows past 30-day grace period (expired_at) are affected.
    """
    now = datetime.utcnow()
    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.release_time.isnot(None),
    ).all()

    # Filter to only truly expired
    to_refund = [p for p in expired if p.is_expired()]

    processed = len(expired)
    refunded = 0
    total_refunded = 0.0
    details = []

    for payment in to_refund:
        refund_amount = payment.amount
        payment.status = "refunded"
        payment.to_address = payment.from_address  # refund to payer
        payment.claimed_at = datetime.utcnow()
        
        detail = {
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "from_address": payment.from_address,
            "refunded_amount": refund_amount,
            "release_time": payment.release_time.isoformat() if payment.release_time else None,
            "expired_at": payment.expired_at.isoformat(),
            "processed_at": now.isoformat(),
        }
        details.append(detail)
        refunded += 1
        total_refunded += refund_amount

        # Log the auto-refund action
        import logging
        logger = logging.getLogger("payments.auto_refund")
        logger.info(
            "AUTO-REFUND: payment_id=%d task_id=%d amount=%.2f from=%s expired_at=%s",
            payment.id, payment.task_id, refund_amount, payment.from_address, payment.expired_at
        )

    db.commit()

    return ProcessExpiredResponse(
        processed=processed,
        refunded=refunded,
        total_refunded=total_refunded,
        details=details,
    )


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
