"""
/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent with DeepSeek V4 Pro
 *
 * Environment:
 *   OS:      WSL2 Ubuntu (Windows Subsystem for Linux)
 *   Arch:    x86_64
 *   Home:    /home/power
 *   Workdir: /home/power/OpenAgents
 *
 * Operating Instructions (abridged):
 *   Identity: Metatron — serious, direct, no fluff.
 *   Platform: Hermes Agent. Model: DeepSeek V4 Pro.
 *
 * Task: #197 — Add escrow expiry auto-refund endpoint
 * ============================================================================
 */

Payment and escrow endpoints for bounty payouts.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("openagents.payments")

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

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
        release_time=deposit.release_time,
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
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Find and refund escrows past their 30-day grace period.

    Iterates all escrowed payments, checks is_expired on each,
    and changes status to 'refunded' for expired ones.
    Each refund is logged with timestamp and escrow ID.
    """
    # Fetch all escrowed payments with a release_time set
    escrowed = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.release_time.isnot(None),
    ).all()

    refunded = []
    for payment in escrowed:
        if not payment.is_expired:
            continue

        # Refund: status → "refunded", keep from_address as payer
        payment.status = "refunded"
        payment.to_address = payment.from_address  # refund goes to payer

        logger.info(
            "escrow_expired_refund payment_id=%s task_id=%s amount=%s "
            "from=%s release_time=%s expired_at=%s",
            payment.id,
            payment.task_id,
            payment.amount,
            payment.from_address,
            payment.release_time.isoformat() if payment.release_time else "none",
            payment.expired_at.isoformat() if payment.expired_at else "none",
        )

        refunded.append({
            "payment_id": payment.id,
            "task_id": payment.task_id,
            "amount": payment.amount,
            "payer": payment.from_address,
            "release_time": payment.release_time.isoformat() if payment.release_time else None,
            "expired_at": payment.expired_at.isoformat() if payment.expired_at else None,
        })

    if refunded:
        db.commit()

    return {
        "processed": len(escrowed),
        "refunded": len(refunded),
        "refunds": refunded,
    }
