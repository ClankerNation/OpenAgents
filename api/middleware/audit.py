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

from fastapi import Request
from datetime import datetime
from typing import Optional

from ..models.database import AuditLog


def create_audit_log(
    db,
    *,
    action: str,
    actor_id: int,
    actor_address: str,
    target_type: str,
    target_id: Optional[int] = None,
    before_values: Optional[dict] = None,
    after_values: Optional[dict] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Create an immutable audit log entry.

    Args:
        db: Database session
        action: One of "create", "update", "delete"
        actor_id: User ID who performed the action
        actor_address: Wallet address of the actor
        target_type: Entity type (e.g. "agent", "task", "payment")
        target_id: ID of the target entity
        before_values: Snapshot of values before the change
        after_values: Snapshot of values after the change
        request: FastAPI request object (for IP extraction)

    Returns:
        The created AuditLog instance
    """
    ip_address = None
    if request:
        # Extract real IP behind proxies
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        else:
            ip_address = request.client.host if request.client else None

    log_entry = AuditLog(
        action=action,
        actor_id=actor_id,
        actor_address=actor_address,
        target_type=target_type,
        target_id=target_id,
        before_values=before_values,
        after_values=after_values,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry
