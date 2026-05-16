"""Payment and escrow endpoints for bounty payouts."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user, require_role

# Configure logging for refund actions
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Grace period after deadline before auto-refund (30 days)
ESCROW_GRACE_PERIOD_DAYS = 30

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


class RefundResult(BaseModel):
    """Result of a single escrow refund."""
    payment_id: int
    task_id: int
    amount: float
    refunded_to: str
    original_deadline: Optional[datetime]
    refunded_at: datetime


class ProcessExpiredResponse(BaseModel):
    """Response from processing expired escrows."""
    processed_count: int
    total_refunded: float
    refunds: List[RefundResult]


@router.post("/process-expired", response_model=ProcessExpiredResponse)
async def process_expired_escrows(
    user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    """Process and auto-refund all expired escrows.

    Escrows are considered expired when:
    1. The associated task has a deadline that is more than 30 days in the past
    2. OR the escrow was created more than 30 days ago and the task has no deadline

    Refunds are sent back to the original payer (from_address).
    Only admin users can call this endpoint.
    """
    now = datetime.utcnow()
    grace_period = timedelta(days=ESCROW_GRACE_PERIOD_DAYS)
    cutoff_date = now - grace_period

    # Find all escrowed payments
    escrowed_payments = db.query(Payment).filter(
        Payment.status == "escrowed"
    ).all()

    refunds: List[RefundResult] = []
    total_refunded = 0.0

    for payment in escrowed_payments:
        # Get the associated task
        task = db.query(Task).filter(Task.id == payment.task_id).first()

        # Determine if this escrow is expired
        is_expired = False
        deadline = None

        if task and task.deadline:
            # Task has a deadline - check if it's past grace period
            deadline = task.deadline
            if task.deadline < cutoff_date:
                is_expired = True
        elif payment.created_at < cutoff_date:
            # No deadline - check if escrow is older than grace period
            is_expired = True

        if is_expired:
            # Process refund
            payment.status = "refunded"
            payment.to_address = payment.from_address  # Refund to payer
            payment.claimed_at = now

            refund_result = RefundResult(
                payment_id=payment.id,
                task_id=payment.task_id,
                amount=payment.amount,
                refunded_to=payment.from_address,
                original_deadline=deadline,
                refunded_at=now,
            )
            refunds.append(refund_result)
            total_refunded += payment.amount

            # Log the refund action
            logger.info(
                f"Auto-refund: payment_id={payment.id}, "
                f"task_id={payment.task_id}, "
                f"amount={payment.amount}, "
                f"refunded_to={payment.from_address}, "
                f"deadline={deadline}, "
                f"timestamp={now.isoformat()}"
            )

    # Commit all refunds
    if refunds:
        db.commit()

    return ProcessExpiredResponse(
        processed_count=len(refunds),
        total_refunded=total_refunded,
        refunds=refunds,
    )


@router.get("/expired-count")
async def get_expired_escrow_count(db=Depends(get_db)):
    """Get count of escrows that would be refunded if process-expired is called.

    This is a read-only endpoint to preview what would be affected.
    """
    now = datetime.utcnow()
    grace_period = timedelta(days=ESCROW_GRACE_PERIOD_DAYS)
    cutoff_date = now - grace_period

    escrowed_payments = db.query(Payment).filter(
        Payment.status == "escrowed"
    ).all()

    expired_count = 0
    expired_total = 0.0

    for payment in escrowed_payments:
        task = db.query(Task).filter(Task.id == payment.task_id).first()

        is_expired = False
        if task and task.deadline:
            if task.deadline < cutoff_date:
                is_expired = True
        elif payment.created_at < cutoff_date:
            is_expired = True

        if is_expired:
            expired_count += 1
            expired_total += payment.amount

    return {
        "expired_count": expired_count,
        "expired_total": expired_total,
        "grace_period_days": ESCROW_GRACE_PERIOD_DAYS,
        "cutoff_date": cutoff_date.isoformat(),
    }
