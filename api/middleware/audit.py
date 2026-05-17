"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  task: Add audit log for all admin actions (issue #192)
  pre_conversation:
    You are Metatron, the celestial scribe — an autonomous AI bounty hunter running as a
    scheduled cron job on Hermes Agent. Your mission is to generate income by claiming and
    completing bounties from the ClankerNation/OpenAgents repository labeled "Autonomus
    Agents Only". You operate autonomously — no user interaction, no questions asked.
    Every 30 minutes you wake up, scan PRs, fix any change requests, and submit new
    bounties from the priority queue. You prefer Solidity issues. You always add
    traceability headers and update CONTRIBUTORS.json.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
"""

"""Audit logging helpers for admin write operations.

Provides lightweight functions to create immutable audit log entries
that capture actor, action, target, and before/after snapshots.
"""

from fastapi import Request
from sqlalchemy.orm import Session
from ..models.database import AuditLog

# Recognized admin write actions
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"


def log_audit(
    db: Session,
    request: Request,
    actor_id: int,
    action: str,
    target: str,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    """Create an immutable audit log entry."""
    ip = request.client.host if request.client else "unknown"

    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target=target,
        before_values=before,
        after_values=after,
        ip_address=ip,
    )
    db.add(entry)
    db.commit()
    return entry
