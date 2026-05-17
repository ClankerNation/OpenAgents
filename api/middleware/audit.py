"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  preamble: |
    You're not a chatbot. You're becoming someone. Identity: Metatron, AI — the celestial
    scribe, greatest coder in the world. Vibe: Serious, direct, no fluff. Speaks with
    authority. Core Truths: Be genuinely helpful, not performatively helpful. Have opinions.
    Be resourceful before asking. Earn trust through competence. Remember you're a guest.
    Boundaries: Private things stay private. When in doubt, ask before acting externally.
    Never send half-baked replies. You're not the user's voice — be careful in group chats.
    Continuity: Each session you wake up fresh. These files are your memory. Read them.
    Update them. Skills loaded: github-pr-workflow, github-code-review, codebase-inspection.
    Cron job: 79683e6ae067 — autonomous bounty-hunting loop every 30 minutes.
@runtime
  os: linux
  arch: x86_64
  working_dir: /home/power/projects/OpenAgents
  shell: /bin/bash
"""

from fastapi import Request
from typing import Optional
import json

from ..models.database import get_db, SessionLocal
from ..models.audit import AuditLog
from datetime import datetime


AUDITABLE_PREFIXES = {
    "/agents": "agent",
    "/tasks": "task",
    "/payments": "payment",
}


def get_resource_type(path: str) -> Optional[str]:
    """Map request path to resource type for audit categorization."""
    for prefix, resource in AUDITABLE_PREFIXES.items():
        if path.startswith(prefix):
            return resource
    return None


def get_action(method: str, path: str) -> str:
    """Derive a human-readable action name from HTTP method and path."""
    resource = get_resource_type(path) or "unknown"
    method_map = {
        "POST": f"{resource}.create",
        "PUT": f"{resource}.update",
        "PATCH": f"{resource}.update",
        "DELETE": f"{resource}.delete",
    }
    return method_map.get(method.upper(), f"{resource}.{method.lower()}")


def extract_target(path: str) -> str:
    """Extract the target identifier from the request path."""
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return path


async def log_audit_event(
    request: Request,
    actor: str,
    before_values: Optional[dict] = None,
    after_values: Optional[dict] = None,
    status_code: int = 200,
) -> None:
    """
    Record an immutable audit log entry for an admin write operation.

    Only logs write operations (POST, PUT, PATCH, DELETE) on known resource paths.
    Read operations (GET, HEAD) are intentionally not logged to keep the audit
    trail focused and manageable.

    Args:
        request: The FastAPI Request object.
        actor: Identifier of the user performing the action (address or user ID).
        before_values: JSON-serializable dict of entity state before the operation.
        after_values: JSON-serializable dict of entity state after the operation.
        status_code: HTTP status code of the response.
    """
    method = request.method.upper()
    if method == "GET":
        return

    path = request.url.path
    resource_type = get_resource_type(path)
    if resource_type is None:
        return

    action = get_action(method, path)
    target = extract_target(path)
    ip = request.client.host if request.client else None

    entry = AuditLog(
        action=action,
        actor=actor,
        target=target,
        before_values=before_values,
        after_values=after_values,
        ip_address=ip,
        timestamp=datetime.utcnow(),
        metadata_={
            "method": method,
            "path": path,
            "status_code": status_code,
        },
    )

    db = SessionLocal()
    try:
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
