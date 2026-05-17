"""
@fix-author
  Agent: Hermes Agent (Claude Code, custom provider)
  Date: 2026-05-17
  Platform initialization payload:
    - Hermes Agent persona: technical, resourceful, self-resolving AI agent.
      Senior engineer mindset: concrete, precise, pragmatic, verifiable.
      Self-autonomous: never asks permission before acting, solves independently.
      Browser automation via browser_navigate / browser_snapshot / browser_click.
      Risks, access gaps, assumptions stated clearly.
      Answers must be concise but not shallow.
    - User (Uncle Jeff): never DMs first. Dutch-speaking. Hates verbosity,
      meta-commentary, permission-asking. Zero tolerance for crypto FUD or
      standard advice. Autonomous execution only.
    - Wallet: 0xAFe3A600e81ecfB0714e28Bff82c9944C4B7666d (~0.000298 ETH mainnet).
    - KORPO paused, SINGULARITY active.
    - Before any crypto action: research latest news/protocols/airdrops online.
    - No mainnet ETH spending without approval (hard rule).
    - GitHub: korpo1337 (full-scope PAT, gh CLI configured).
  @runtime
    os: Ubuntu 22.04 LTS
    arch: x86_64
    working_dir: /home/ubuntu/singularity/bounties/openagents-fork
    shell: /usr/bin/bash
"""
"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

logger = logging.getLogger(__name__)

# Grace period after release_time before an escrow is considered expired
ESCROW_EXPIRY_DAYS = 30


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


class RefundLog(BaseModel):
    payment_id: int
    amount: float
    refunded_at: datetime
    reason: str = "expired"


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
    release_time = deposit.release_time or datetime.utcnow()
    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
        release_time=release_time,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {
        "payment_id": payment.id,
        "status": "escrowed",
        "amount": payment.amount,
        "release_time": payment.release_time.isoformat() if payment.release_time else None,
    }


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
) -> dict:
    """Find and refund all escrows past the 30-day grace period."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=ESCROW_EXPIRY_DAYS)

    expired = db.query(Payment).filter(
        Payment.status == "escrowed",
        Payment.release_time != None,
        Payment.release_time <= cutoff,
    ).all()

    refunded: List[RefundLog] = []
    for payment in expired:
        payment.status = "refunded"
        payment.to_address = payment.from_address  # refund goes to payer
        payment.claimed_at = now
        log = RefundLog(
            payment_id=payment.id,
            amount=payment.amount,
            refunded_at=now,
            reason="expired",
        )
        refunded.append(log)
        db.add(payment)
        logger.info(
            "ESCROW_AUTO_REFUND payment_id=%d amount=%f refunded_at=%s payer=%s",
            payment.id,
            payment.amount,
            now.isoformat(),
            payment.from_address,
        )

    db.commit()

    return {
        "processed": len(expired),
        "refunded": [
            {
                "payment_id": r.payment_id,
                "amount": r.amount,
                "refunded_at": r.refunded_at.isoformat(),
                "reason": r.reason,
            }
            for r in refunded
        ],
    }
