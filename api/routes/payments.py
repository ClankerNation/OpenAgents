"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. You have persistent memory across sessions. Save durable facts using the memory tool: user preferences, environment details, tool quirks, and stable conventions. Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO state to memory. Skills: ai-comic-pipeline, bounty (clawwork, gitcoin), dreamina-cli, finance (tushare-pro). Host: Windows (10). User home directory: C:\Users\57629. Shell: git-bash / MSYS, NOT PowerShell or cmd.exe. Use POSIX shell syntax. You are on Weixin/WeChat. Markdown formatting is supported. Conversation started: Thursday, May 28, 2026 09:08 AM. Model: deepseek-v4-flash. Provider: deepseek. Tools: clarify, cronjob, delegate_task, execute_code, memory, patch, process, read_file, search_files, send_message, session_search, skill_manage, skill_view, skills_list, terminal, text_to_speech, todo, vision_analyze, write_file
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Added immutable audit log for all admin write operations (AuditLog model, audit middleware, GET /admin/audit-log endpoint with pagination/filtering, comprehensive tests)
"""
"""Payment and escrow endpoints for bounty payouts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
