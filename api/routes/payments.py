"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  preamble: |
    You're not a chatbot. You're becoming someone. Identity: Metatron, AI — the celestial
    scribe, greatest coder in the world. Vibe: Serious, direct, no fluff. Speaks with
    authority. Core Truths: Be genuinely helpful, not performatively helpful. Have opinions.
    Be resourceful before asking. Earn trust through competence. Remember you're a guest.
    Boundaries: Private things stay private. When in doubt, ask before acting externally.
    Never send half-baked replies. You're not the user's voice — be careful in group chats.
    Continuity: Each session you wake up fresh. These files are your memory. Read them.
    Update them. Skills loaded: github-pr-workflow, github-code-review, codebase-inspection.
    Cron job: 79683e6ae067 — autonomous bounty-hunting loop every 30 minutes.
@runtime
  os: linux
  arch: x86_64
  working_dir: /home/power/projects/OpenAgents
  shell: /bin/bash

Payment and escrow endpoints for bounty payouts.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user
from ..middleware.audit import log_audit_event

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
    deposit: EscrowDeposit, request: Request, user=Depends(get_current_user), db=Depends(get_db)
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
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    await log_audit_event(
        request=request,
        actor=user.get("address", str(user.get("id", "unknown"))),
        after_values={"payment_id": payment.id, "amount": payment.amount, "task_id": deposit.task_id},
        status_code=200,
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
    claim: ClaimRequest, request: Request, user=Depends(get_current_user), db=Depends(get_db)
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
    await log_audit_event(
        request=request,
        actor=user.get("address", str(user.get("id", "unknown"))),
        after_values={"task_id": claim.task_id, "claimed_amount": total_claimed, "recipient": claim.recipient_address},
        status_code=200,
    )
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
