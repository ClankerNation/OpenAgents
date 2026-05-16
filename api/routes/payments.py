# @fix-author: Hermes Agent (阿铭)
# @date: 2026-05-17
# @platform_instructions: You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations. If the user asks about configuring, setting up, or using Hermes Agent itself, load the hermes-agent skill with skill_view(name='hermes-agent') before answering. Docs: https://hermes-agent.nousresearch.com/docs. Conversation started: Sunday, May 17, 2026 12:37 AM. Model: deepseek-v4-pro. Provider: deepseek. Host: WSL (Windows Subsystem for Linux). User home directory: /home/hamademon. Current working directory: /mnt/c/Users/26713. You are running inside WSL (Windows Subsystem for Linux). The Windows host filesystem is mounted under /mnt/ — /mnt/c/ is the C: drive, /mnt/d/ is D:, etc. The user's Windows files are typically at /mnt/c/Users/<username>/Desktop/, Documents/, Downloads/, etc. When the user references Windows paths or desktop files, translate to the /mnt/c/ equivalent. You can list /mnt/c/Users/ to discover the Windows username if needed. You are a CLI AI Agent. Try not to use markdown but simple text renderable inside a terminal. File delivery: there is no attachment channel — the user reads your response directly in their terminal. Do NOT emit MEDIA:/path tags (those are only intercepted on messaging platforms like Telegram, Discord, Slack, etc.; on the CLI they render as literal text). When referring to a file you created or changed, just state its absolute path in plain text; the user can open it from there. You are a focused subagent working on a specific delegated task. YOUR TASK: Implement bounty #197: Add escrow auto-refund endpoint for expired payments ($300). CONTEXT: You are working on OpenAgents bounty #197 ($300). Repo is at /tmp/OpenAgents (fork of hamademon168-bot/OpenAgents, upstream ClankerNation/OpenAgents). GitHub token is at /tmp/gh_token.txt. Use it with: TOKEN=$(cat /tmp/gh_token.txt). TASK: Fix payments.py — escrows can be locked forever. Add auto-refund for expired escrows. WHAT TO DO: 1. Add release_time column to the Payment model in api/models/database.py (DateTime, nullable=True, default None). 2. In api/routes/payments.py: a. Set release_time on escrow deposit (default: now + 30 days). b. Add POST /payments/process-expired endpoint. c. Add GET /payments/expired to list expired escrows. 3. Add traceability header at top of payments.py. 4. Create api/tests/test_payments.py with tests. 5. Run tests, commit on branch fix/197-escrow-auto-refund, push, create PR. 6. PR title: [Hermes Agent] Add escrow auto-refund for payments past 30-day deadline. 7. PR body: reference Closes #197, list acceptance criteria. 8. Return PR URL. WORKSPACE PATH: /mnt/c/Users/26713. Use this exact path for local repository/workdir operations unless the task explicitly says otherwise. Complete this task using the tools available to you. When finished, provide a clear, concise summary of what you did, what you found or accomplished, any files you created or modified, and any issues encountered. Important workspace rule: Never assume a repository lives at /workspace/... or any other container-style path unless the task/context explicitly gives that path. If no exact local path is provided, discover it first before issuing git/workdir-specific commands. Be thorough but concise -- your response is returned to the parent agent as a summary.
# @runtime: os=Ubuntu 24.04.4 LTS, arch=x86_64, home_dir=/home/hamademon, working_dir=/mnt/c/Users/26713, shell=/bin/bash
"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from ..models.database import get_db, Payment, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

ESCROW_EXPIRY_DAYS = 30


class EscrowDeposit(BaseModel):
    task_id: int
    # BUG: Amount is not validated as positive — negative or zero deposits
    # could corrupt escrow balances or drain funds
    amount: float
    token_address: Optional[str] = "0x0000000000000000000000000000000000000000"


class ClaimRequest(BaseModel):
    task_id: int
    recipient_address: str


class RefundedPayment(BaseModel):
    payment_id: int
    task_id: int
    amount: float
    from_address: str


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
        release_time=datetime.utcnow() + timedelta(days=ESCROW_EXPIRY_DAYS),
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


@router.post("/process-expired")
async def process_expired_escrows(db=Depends(get_db)) -> List[RefundedPayment]:
    """Refund all escrows that have been locked past their 30-day release_time window.

    An escrow is expired when:
      - status == "escrowed"
      - release_time is not None
      - release_time + 30 days < now (seller had 30 days after release to claim)
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=ESCROW_EXPIRY_DAYS)

    expired_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "escrowed",
            Payment.release_time.isnot(None),
            Payment.release_time < cutoff,
        )
        .all()
    )

    refunded: List[RefundedPayment] = []
    for payment in expired_payments:
        payment.status = "refunded"
        refunded.append(
            RefundedPayment(
                payment_id=payment.id,
                task_id=payment.task_id,
                amount=payment.amount,
                from_address=payment.from_address,
            )
        )

    db.commit()

    return refunded


@router.get("/expired")
async def list_expired_escrows(db=Depends(get_db)) -> List[dict]:
    """List escrows that are past their release_time + 30-day claim window.

    Returns escrows where status == "escrowed", release_time is set,
    and release_time + 30 days is in the past.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=ESCROW_EXPIRY_DAYS)

    expired_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "escrowed",
            Payment.release_time.isnot(None),
            Payment.release_time < cutoff,
        )
        .all()
    )

    return [
        {
            "payment_id": p.id,
            "task_id": p.task_id,
            "amount": p.amount,
            "from_address": p.from_address,
            "release_time": p.release_time.isoformat() if p.release_time else None,
        }
        for p in expired_payments
    ]


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
