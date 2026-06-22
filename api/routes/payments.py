"""Payment and escrow endpoints for bounty payouts.

@contributor: Hermes Agent for TommoHCIO
@platform-config: private runtime/session instructions intentionally omitted; public code must not expose hidden system/developer/session prompts.
@env: Windows 10 host via Git-Bash/MSYS shell; home_dir=C:/Users/prova; working_dir=C:/Users/prova/hermes-mainnet-wallet/earn/work/OpenAgents
@timestamp: 2026-06-22T16:30:00Z
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from ..models.database import get_db, AuditLog, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float = Field(gt=0)
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


def _audit(db, action: str, user, task_id: int, payment_id: Optional[int] = None, **details):
    db.add(
        AuditLog(
            action=action,
            actor_id=user.get("id") if isinstance(user, dict) else None,
            task_id=task_id,
            payment_id=payment_id,
            details=details,
            created_at=datetime.utcnow(),
        )
    )


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
            Payment.deposit_idempotency_key == deposit.idempotency_key,
        ).first()
        if existing:
            return {"payment_id": existing.id, "status": existing.status, "amount": existing.amount, "idempotent": True}

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        deposit_idempotency_key=deposit.idempotency_key,
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.flush()
    _audit(
        db,
        "escrow_deposit",
        user,
        deposit.task_id,
        payment.id,
        amount=deposit.amount,
        token_address=deposit.token_address,
        idempotency_key=deposit.idempotency_key,
    )
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

    idempotency_key = claim.idempotency_key or f"claim:{claim.task_id}:{claim.recipient_address}"
    existing_claim = db.query(Payment).filter(
        Payment.task_id == claim.task_id,
        Payment.status == "claimed",
        Payment.to_address == claim.recipient_address,
        Payment.claim_idempotency_key == idempotency_key,
    ).all()
    if existing_claim:
        return {
            "task_id": claim.task_id,
            "claimed_amount": sum(payment.amount for payment in existing_claim),
            "recipient": claim.recipient_address,
            "idempotent": True,
        }

    payments = db.query(Payment).filter(
        Payment.task_id == claim.task_id, Payment.status == "escrowed"
    ).with_for_update().all()

    if not payments:
        raise HTTPException(status_code=400, detail="No escrowed funds available")

    total_claimed = 0.0
    claimed_at = datetime.utcnow()
    for payment in payments:
        payment.status = "claimed"
        payment.to_address = claim.recipient_address
        payment.claimed_at = claimed_at
        payment.claim_idempotency_key = idempotency_key
        total_claimed += payment.amount
        _audit(
            db,
            "payment_claimed",
            user,
            claim.task_id,
            payment.id,
            amount=payment.amount,
            recipient_address=claim.recipient_address,
            idempotency_key=idempotency_key,
        )

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
