# @fix-author rafaio1
# @date 2026-08-25T04:30:00Z
# @runtime linux x64 /tmp/openagents_issue_197 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for escrow expiry auto-refund (Issue #197)
"""Payment and escrow endpoints for bounty payouts.

Implements strict input validation, idempotency protection, optimistic locking
for claims, and an auto-refund endpoint for expired escrows per Issue #197.

Closes #197
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update

from ..middleware.auth import get_current_user
from ..models.database import Payment, Task, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

ESCROW_GRACE_PERIOD_DAYS = 30


class EscrowDeposit(BaseModel):
    """Validated escrow deposit payload."""

    task_id: int = Field(..., ge=1)
    amount: float = Field(..., gt=0, description="Must be strictly positive")
    token_address: str = Field(
        default="0x0000000000000000000000000000000000000000",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )


class ClaimRequest(BaseModel):
    """Validated claim payload."""

    task_id: int = Field(..., ge=1)
    recipient_address: str = Field(..., pattern=r"^0x[a-fA-F0-9]{40}$")


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit,
    user=Depends(get_current_user),
    db=Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """Create an escrow deposit with idempotency protection."""
    task = db.query(Task).filter(Task.id == deposit.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # Idempotency: check if a payment with this key already exists
    if idempotency_key:
        existing = (
            db.query(Payment)
            .filter(Payment.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return {
                "payment_id": existing.id,
                "status": existing.status,
                "amount": existing.amount,
                "idempotent": True,
            }

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
    )
    if idempotency_key:
        payment.idempotency_key = idempotency_key

    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_id": payment.id, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: int = Field(..., ge=1), db=Depends(get_db)):
    payments = db.query(Payment).filter(
        Payment.task_id == task_id, Payment.status == "escrowed"
    ).all()
    total = sum(p.amount for p in payments)
    return {"task_id": task_id, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Claim escrowed funds with optimistic locking to prevent double-payout."""
    task = db.query(Task).filter(Task.id == claim.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # Optimistic lock: atomic UPDATE ... WHERE status='escrowed' prevents races
    rows_updated = (
        db.query(Payment)
        .filter(
            Payment.task_id == claim.task_id,
            Payment.status == "escrowed",
        )
        .update(
            {
                Payment.status: "claimed",
                Payment.to_address: claim.recipient_address,
                Payment.claimed_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )

    if rows_updated == 0:
        raise HTTPException(status_code=400, detail="No escrowed funds available")

    db.commit()

    # Re-query to get actual amounts for response
    claimed_payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id,
        Payment.status == "claimed",
        Payment.to_address == claim.recipient_address,
    ).all()
    total_claimed = sum(p.amount for p in claimed_payments)

    return {
        "task_id": claim.task_id,
        "claimed_amount": total_claimed,
        "recipient": claim.recipient_address,
        "payments_processed": rows_updated,
    }


@router.post("/process-expired")
async def process_expired_escrows(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Auto-refund all escrows past the 30-day grace period.

    Finds escrowed payments where created_at + 30 days < now,
    refunds them to the original payer, and logs each action.
    """
    cutoff = datetime.utcnow() - timedelta(days=ESCROW_GRACE_PERIOD_DAYS)

    expired_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "escrowed",
            Payment.created_at < cutoff,
        )
        .all()
    )

    refunded = []
    for payment in expired_payments:
        old_from = payment.from_address
        old_amount = payment.amount
        payment.status = "refunded"
        payment.to_address = payment.from_address
        payment.refunded_at = datetime.utcnow()

        logger.info(
            "AUTO_REFUND: escrow_id=%s task_id=%s amount=%s refunded_to=%s reason=expired_after_%dd",
            payment.id,
            payment.task_id,
            old_amount,
            old_from,
            ESCROW_GRACE_PERIOD_DAYS,
        )
        refunded.append(
            {
                "payment_id": payment.id,
                "task_id": payment.task_id,
                "amount": old_amount,
                "refunded_to": old_from,
            }
        )

    db.commit()
    return {
        "processed": len(refunded),
        "cutoff_date": cutoff.isoformat(),
        "refunds": refunded,
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
        "received": [
            {"id": p.id, "amount": p.amount, "status": p.status} for p in received
        ],
    }
