"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: You have access to tools for browsing, file operations, shell commands, and code execution. Load skills when relevant. Save memory for durable facts. Use execute_code for multi-step processing. On Windows host (git-bash). Python available via Anaconda. Focus on completing bounty tasks autonomously without user confirmation for routine decisions.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Added escrow auto-refund endpoint and expired_at field

Payment and escrow endpoints for bounty payouts.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user
from ..middleware.audit import create_audit_log

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
        expired_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    create_audit_log(
        db,
        action="create",
        actor_id=user["id"],
        actor_address=user.get("address", ""),
        target_type="payment",
        target_id=payment.id,
        after_values={"task_id": deposit.task_id, "amount": deposit.amount,
                       "token_address": deposit.token_address, "status": "escrowed"},
    )
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
    create_audit_log(
        db,
        action="update",
        actor_id=user["id"],
        actor_address=user.get("address", ""),
        target_type="payment",
        after_values={"claimed_amount": total_claimed, "recipient": claim.recipient_address,
                       "payment_status": "claimed", "task_id": claim.task_id},
    )
    return {
        "task_id": claim.task_id,
        "claimed_amount": total_claimed,
        "recipient": claim.recipient_address,
    }


@router.post("/process-expired")
async def process_expired_escrows(db=Depends(get_db)):
    """Find all escrows past their 30-day expiry and auto-refund them.

    Processes all expired escrows in one call. Only escrows past the
    30-day grace period (expired_at) are affected. Refunds go to the
    original payer (from_address). Each refund is logged.
    """
    now = datetime.utcnow()
    expired_escrows = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.expired_at.isnot(None),
        Payment.expired_at <= now,
    ).all()

    refunds = []
    for escrow in expired_escrows:
        escrow.status = "refunded"
        escrow.to_address = escrow.from_address
        escrow.claimed_at = now
        refunds.append({
            "escrow_id": escrow.id,
            "task_id": escrow.task_id,
            "amount": escrow.amount,
            "refunded_to": escrow.from_address,
            "timestamp": now.isoformat(),
        })
        create_audit_log(
            db,
            action="update",
            actor_id=0,
            actor_address="system",
            target_type="payment",
            target_id=escrow.id,
            before_values={"status": "escrowed"},
            after_values={"status": "refunded", "refunded_to": escrow.from_address},
        )

    db.commit()
    return {"processed": len(refunds), "refunds": refunds}


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
