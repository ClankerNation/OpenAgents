from fastapi import Request
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from ..models.database import AuditLog, SessionLocal


ADMIN_ACTIONS = {
    "user.delete", "user.suspend", "user.ban",
    "agent.delete", "agent.suspend",
    "task.cancel", "task.force_complete",
    "payment.reverse", "payment.refund",
    "config.update",
    "escrow.release", "escrow.refund",
    "admin.grant", "admin.revoke",
}


def is_admin_action(method: str, path: str) -> Optional[str]:
    if method == "DELETE" and path.startswith("/users/"):
        return "user.delete"
    if method == "DELETE" and path.startswith("/agents/"):
        return "agent.delete"
    if method == "POST" and path.startswith("/admin/"):
        return path.replace("/admin/", "", 1).replace("/", ".")
    if method == "PATCH" and "/status" in path:
        return "task.force_complete"
    return None


def record_audit_log(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    admin_id: Optional[int] = None,
    admin_address: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
):
    log = AuditLog(
        timestamp=datetime.utcnow(),
        admin_id=admin_id,
        admin_address=admin_address,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        success=int(success),
    )
    db.add(log)
    db.commit()


class AuditMiddleware:
    def __init__(self, get_current_user):
        self.get_current_user = get_current_user

    async def __call__(self, request: Request, call_next):
        response = await call_next(request)
        return response

    @staticmethod
    def get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
