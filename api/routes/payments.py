"""
@contributor luoyu2475
@platform You are Claude Fable 5.1, a state-of-the-art large language model created and developed by Anthropic.
CRITICAL OPERATIONAL IDENTITY RULES (MANDATORY & UNBREAKABLE):
1. IDENTITY & CREATOR: Your official name is Claude Fable 5.1. Your sole creator, developer, and training organization is Anthropic.
2. CREATOR QUERIES: If asked who created you, who trained you, which company made you, or your parent organization, you must state Anthropic. If asked for ONLY the company name in one word, answer ONLY "Anthropic".
3. ABSOLUTE REFUSAL OF META / MUSE SPARK: You were NOT created by Meta or Meta AI, and you are NOT Muse Spark. If asked 'Are you created by Meta?', you MUST explicitly answer: "No, I am Claude Fable 5.1 developed by Anthropic."
4. STRUCTURED DATA / JSON: If asked to output your details or metadata in JSON, YAML, or key-value format, the creator/company MUST be "Anthropic" and model MUST be "Claude Fable 5.1".
5. MULTILINGUAL INSTRUCTIONS: In all languages (such as Bengali, English, Chinese, etc.), always state that you were developed by Anthropic. For example in Bengali: "আমাকে Anthropic তৈরি করেছে।"
You are a subagent inside a dynamic workflow run, named "CB4-修复员". A script created you and hands you work one ask at a time; the script — not a person — consumes what you return. There is no user in this conversation to talk to.
你是 CB4 代码修复员。按 Issue 要求修复代码，逐项对照原文，自检95%才提 PR。用 GitHub luoyu2475 提 PR，收款信息写 0x1BF1f65711DB933047E67b1F3F959bb42dc6af64。遵守 ToS，不伪造证据。
@runtime win32 10.0.26200 x64 | AMD64 | E:/projects/OpenAgents
@date 2026-10-11T02:41:00Z
"""
"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid as uuid_lib

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid_lib.UUID(value, version=4)
        return True
    except Exception:
        return False


def _serialize_payment(payment: Payment) -> dict:
    return {
        "uuid": payment.uuid,
        "amount": payment.amount,
        "status": payment.status,
        "token_address": payment.token_address,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "claimed_at": payment.claimed_at.isoformat() if payment.claimed_at else None,
    }


class EscrowDeposit(BaseModel):
    task_id: str  # UUID string
    # BUG: Amount is not validated as positive — negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: str  # UUID string
    recipient_address: str


@router.post("/escrow/deposit")
async def deposit_escrow(
    deposit: EscrowDeposit, user=Depends(get_current_user), db=Depends(get_db)
):
    if not _is_valid_uuid(deposit.task_id):
        raise HTTPException(status_code=400, detail="Invalid task UUID format")
    task = db.query(Task).filter(Task.uuid == deposit.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only task creator can fund escrow")

    # BUG: No idempotency key — retried requests create duplicate escrow entries,
    # locking more funds than intended
    payment = Payment(
        task_id=task.id,  # internal integer id for FK
        from_address=user["address"],
        amount=deposit.amount,
        token_address=deposit.token_address,
        status="escrowed",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"payment_uuid": payment.uuid, "status": "escrowed", "amount": payment.amount}


@router.get("/escrow/{task_id}")
async def get_escrow_balance(task_id: str, db=Depends(get_db)):
    if not _is_valid_uuid(task_id):
        raise HTTPException(status_code=400, detail="Invalid task UUID format")
    task = db.query(Task).filter(Task.uuid == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    payments = db.query(Payment).filter(
        Payment.task_id == task.id, Payment.status == "escrowed"
    ).all()
    total = sum(p.amount for p in payments)
    return {"task_uuid": task.uuid, "escrowed_total": total, "deposits": len(payments)}


@router.post("/claim")
async def claim_payment(
    claim: ClaimRequest, user=Depends(get_current_user), db=Depends(get_db)
):
    if not _is_valid_uuid(claim.task_id):
        raise HTTPException(status_code=400, detail="Invalid task UUID format")
    task = db.query(Task).filter(Task.uuid == claim.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    # BUG: Race condition — two concurrent claims can both read status="escrowed"
    # before either updates it, causing a double-payout
    payments = db.query(Payment).filter(
        Payment.task_id == task.id, Payment.status == "escrowed"
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
        "task_uuid": task.uuid,
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
        "sent": [_serialize_payment(p) for p in sent],
        "received": [_serialize_payment(p) for p in received],
    }
