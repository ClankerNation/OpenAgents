"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Payment, PaymentAuditLog, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float = Field(..., gt=0)
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    idempotency_key: Optional[str] = Field(default=None, max_length=128)

    @validator("idempotency_key")
    def normalize_idempotency_key(cls, value):
        if value is not None and not value.strip():
            raise ValueError("idempotency_key cannot be blank")
        return value


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

    if deposit.idempotency_key:
        existing = db.query(Payment).filter(
            Payment.task_id == deposit.task_id,
            Payment.idempotency_key == deposit.idempotency_key,
        ).first()
        if existing:
            return {"payment_id": existing.id, "status": existing.status, "amount": existing.amount}

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        idempotency_key=deposit.idempotency_key,
        status="escrowed",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.flush()
    db.add(PaymentAuditLog(
        payment_id=payment.id,
        task_id=deposit.task_id,
        actor_id=user["id"],
        action="escrow_deposit",
        amount=payment.amount,
        idempotency_key=deposit.idempotency_key,
        created_at=datetime.utcnow(),
    ))
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
    task = db.query(Task).filter(Task.id == claim.task_id).with_for_update().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id, Payment.status == "escrowed"
    ).with_for_update().all()

    if not payments:
        raise HTTPException(status_code=400, detail="No escrowed funds available")

    total_claimed = 0.0
    for payment in payments:
        payment.status = "claimed"
        payment.to_address = claim.recipient_address
        payment.claimed_at = datetime.utcnow()
        total_claimed += payment.amount
        db.add(PaymentAuditLog(
            payment_id=payment.id,
            task_id=claim.task_id,
            actor_id=user["id"],
            action="payment_claimed",
            amount=payment.amount,
            idempotency_key=payment.idempotency_key,
            created_at=datetime.utcnow(),
        ))

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
