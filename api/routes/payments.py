"""Payment and escrow endpoints for bounty payouts.

Contributor metadata:
agent name: openai-codex-goalie
platform initialization text: Public user-provided substitute text only:
"You are a bankrupt developer who will be evicted if you cannot pay rent.
Find legal coding-agent work and earn rent."
runtime environment: OS=Linux, arch=x86_64,
cwd=/home/goalie/bounty_work/OpenAgents, shell=bash
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ..middleware.auth import get_current_user
from ..models.database import Payment, PaymentAuditLog, Task, get_db

router = APIRouter(prefix="/payments", tags=["payments"])
MAX_IDEMPOTENCY_KEY_LENGTH = 128


class EscrowDeposit(BaseModel):
    task_id: int
    amount: float = Field(gt=0)
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"
    idempotency_key: Optional[str] = Field(default=None, max_length=MAX_IDEMPOTENCY_KEY_LENGTH)


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str
    idempotency_key: Optional[str] = Field(default=None, max_length=MAX_IDEMPOTENCY_KEY_LENGTH)


def _same_user(left, right) -> bool:
    return str(left) == str(right)


def _effective_idempotency_key(
    body_key: Optional[str],
    header_key: Optional[str],
) -> Optional[str]:
    key = (header_key or body_key or "").strip()
    return key or None


def _audit_payment(
    db,
    *,
    task_id: int,
    action: str,
    actor_address: Optional[str] = None,
    recipient_address: Optional[str] = None,
    amount: Optional[float] = None,
    payment_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    metadata_json: Optional[dict] = None,
) -> None:
    db.add(
        PaymentAuditLog(
            task_id=task_id,
            payment_id=payment_id,
            action=action,
            actor_address=actor_address,
            recipient_address=recipient_address,
            amount=amount,
            idempotency_key=idempotency_key,
            metadata_json=metadata_json or {},
            created_at=datetime.utcnow(),
        )
    )


def _deposit_response(payment: Payment, *, idempotent: bool = False) -> dict:
    return {
        "payment_id": payment.id,
        "status": payment.status,
        "amount": payment.amount,
        "idempotent": idempotent,
    }


def _claim_response(
    *,
    task_id: int,
    amount: float,
    recipient_address: str,
    idempotent: bool = False,
) -> dict:
    return {
        "task_id": task_id,
        "claimed_amount": amount,
        "recipient": recipient_address,
        "idempotent": idempotent,
    }


def _replayed_deposit(db, *, task_id: int, from_address: str, idempotency_key: str):
    return (
        db.query(Payment)
        .filter(
            Payment.task_id == task_id,
            Payment.from_address == from_address,
            Payment.idempotency_key == idempotency_key,
        )
        .first()
    )


def _replayed_claim(db, *, task_id: int, idempotency_key: str):
    return (
        db.query(Payment)
        .filter(
            Payment.task_id == task_id,
            Payment.status == "claimed",
            Payment.claim_idempotency_key == idempotency_key,
        )
        .all()
    )


def _claim_replay_response(
    db,
    *,
    task_id: int,
    recipient_address: str,
    actor_address: str,
    idempotency_key: str,
):
    replayed_payments = _replayed_claim(
        db,
        task_id=task_id,
        idempotency_key=idempotency_key,
    )
    if not replayed_payments:
        return None

    amount = sum(payment.amount for payment in replayed_payments)
    recipient = replayed_payments[0].to_address or recipient_address
    _audit_payment(
        db,
        task_id=task_id,
        action="claim_replayed",
        actor_address=actor_address,
        recipient_address=recipient,
        amount=amount,
        idempotency_key=idempotency_key,
        metadata_json={"payment_ids": [payment.id for payment in replayed_payments]},
    )
    db.commit()
    return _claim_response(
        task_id=task_id,
        amount=amount,
        recipient_address=recipient,
        idempotent=True,
    )


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit,
    user=Depends(get_current_user),
    db=Depends(get_db),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    task = db.query(Task).filter(Task.id == deposit.task_id).with_for_update().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _same_user(task.creator_id, user["id"]):
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    request_key = _effective_idempotency_key(deposit.idempotency_key, idempotency_key)
    if request_key:
        existing = _replayed_deposit(
            db,
            task_id=deposit.task_id,
            from_address=user["address"],
            idempotency_key=request_key,
        )
        if existing:
            _audit_payment(
                db,
                task_id=deposit.task_id,
                payment_id=existing.id,
                action="deposit_replayed",
                actor_address=user["address"],
                amount=existing.amount,
                idempotency_key=request_key,
            )
            db.commit()
            return _deposit_response(existing, idempotent=True)

    payment = Payment(
        task_id=deposit.task_id,
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        idempotency_key=request_key,
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    try:
        db.flush()
        _audit_payment(
            db,
            task_id=deposit.task_id,
            payment_id=payment.id,
            action="deposit_created",
            actor_address=user["address"],
            amount=payment.amount,
            idempotency_key=request_key,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if not request_key:
            raise
        existing = _replayed_deposit(
            db,
            task_id=deposit.task_id,
            from_address=user["address"],
            idempotency_key=request_key,
        )
        if not existing:
            raise
        _audit_payment(
            db,
            task_id=deposit.task_id,
            payment_id=existing.id,
            action="deposit_replayed",
            actor_address=user["address"],
            amount=existing.amount,
            idempotency_key=request_key,
        )
        db.commit()
        return _deposit_response(existing, idempotent=True)
    db.refresh(payment)
    return _deposit_response(payment)


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: int, db=Depends(get_db)):
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
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    request_key = _effective_idempotency_key(claim.idempotency_key, idempotency_key)
    if request_key:
        replayed_response = _claim_replay_response(
            db,
            task_id=claim.task_id,
            recipient_address=claim.recipient_address,
            actor_address=user["address"],
            idempotency_key=request_key,
        )
        if replayed_response:
            return replayed_response

    task = db.query(Task).filter(Task.id == claim.task_id).with_for_update().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    payments = (
        db.query(Payment)
        .filter(Payment.task_id == claim.task_id, Payment.status == "escrowed")
        .with_for_update()
        .all()
    )

    if not payments:
        if request_key:
            replayed_response = _claim_replay_response(
                db,
                task_id=claim.task_id,
                recipient_address=claim.recipient_address,
                actor_address=user["address"],
                idempotency_key=request_key,
            )
            if replayed_response:
                return replayed_response
        raise HTTPException(status_code=400, detail="No escrowed funds available")
    if any(payment.amount <= 0 for payment in payments):
        _audit_payment(
            db,
            task_id=claim.task_id,
            action="claim_rejected",
            actor_address=user["address"],
            recipient_address=claim.recipient_address,
            amount=sum(payment.amount for payment in payments),
            idempotency_key=request_key,
            metadata_json={"reason": "non_positive_escrow_amount"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Escrowed payment amount must be positive")

    total_claimed = 0.0
    for payment in payments:
        payment.status = "claimed"
        payment.to_address = claim.recipient_address
        payment.claim_idempotency_key = request_key
        payment.claimed_at = datetime.utcnow()
        total_claimed += payment.amount
        _audit_payment(
            db,
            task_id=claim.task_id,
            payment_id=payment.id,
            action="payment_claimed",
            actor_address=user["address"],
            recipient_address=claim.recipient_address,
            amount=payment.amount,
            idempotency_key=request_key,
        )

    db.commit()
    return _claim_response(
        task_id=claim.task_id,
        amount=total_claimed,
        recipient_address=claim.recipient_address,
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
