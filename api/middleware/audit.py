"""Audit logging service and middleware for the OpenAgents API.

Logs all admin actions (create, update, delete resources, config changes)
to the database with timestamp, actor, action, resource, and details.

@generated-by: hermes-agent-scotia1973
@bounty: #192
@description: Add audit log for all admin actions
"""

from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db, AuditLog


def log_admin_action(
    db: Session,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    actor_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Record an admin action in the audit log.

    Args:
        db: SQLAlchemy database session.
        actor_id: Unique identifier of the actor performing the action.
        action: The action performed (e.g. 'create', 'update', 'delete', 'config_change').
        resource_type: Type of resource affected (e.g. 'agent', 'task', 'payment').
        resource_id: Identifier of the affected resource, if applicable.
        actor_address: Blockchain address of the actor, if known.
        details: Arbitrary JSON-serializable details about the action.
        request: FastAPI Request object (for IP and user-agent extraction).

    Returns:
        The created AuditLog instance.
    """
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        actor_id=str(actor_id),
        actor_address=actor_address,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=details or {},
        ip_address=_get_client_ip(request) if request else None,
        user_agent=_get_user_agent(request) if request else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _get_user_agent(request: Request) -> Optional[str]:
    """Extract User-Agent header from request."""
    ua = request.headers.get("User-Agent")
    return ua[:512] if ua and len(ua) > 512 else ua


# Standard audit action constants
ACTION_CREATE = "create"
ACTION_READ = "read"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_STATUS_CHANGE = "status_change"
ACTION_CONFIG_CHANGE = "config_change"
ACTION_LOGIN = "login"
ACTION_CLAIM = "claim"
ACTION_DEPOSIT = "deposit"

# Resource type constants
RESOURCE_AGENT = "agent"
RESOURCE_TASK = "task"
RESOURCE_PAYMENT = "payment"
RESOURCE_USER = "user"
RESOURCE_CONFIG = "config"
RESOURCE_AUDIT_LOG = "audit_log"
