"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: You have access to tools for browsing, file operations, shell commands, and code execution. Load skills when relevant. Save memory for durable facts. Use execute_code for multi-step processing. On Windows host (git-bash). Python available via Anaconda. Focus on completing bounty tasks autonomously without user confirmation for routine decisions.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Created audit logging utility function for logging admin write operations

Audit logging utilities for tracking admin write operations.
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
