"""
Audit log model for admin action tracking.

@contributor-info
agent: QClaw
date: 2026-05-18

"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum

class AuditAction(str, Enum):
    """Types of auditable admin actions."""
    AGENT_REGISTER = "agent_register"
    AGENT_UPDATE = "agent_update"
    AGENT_DEACTIVATE = "agent_deactivate"
    TASK_CREATE = "task_create"
    TASK_CANCEL = "task_cancel"
    TASK_ASSIGN = "task_assign"
    PAYMENT_RELEASE = "payment_release"
    PAYMENT_REFUND = "payment_refund"
    PARAMETER_CHANGE = "parameter_change"
    USER_ROLE_CHANGE = "user_role_change"
    USER_BAN = "user_ban"
    USER_UNBAN = "user_unban"

class AuditLog(BaseModel):
    """Immutable audit log entry for admin actions."""
    id: int
    action: AuditAction
    actor: str = Field(..., description="Address or ID of the admin who performed the action")
    target: str = Field(..., description="ID of the affected entity")
    target_type: str = Field(..., description="Type of the affected entity (agent, task, user, etc.)")
    before: Optional[dict] = Field(None, description="State before the action")
    after: Optional[dict] = Field(None, description="State after the action")
    ip_address: str = Field(..., description="IP address of the actor")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "action": "agent_deactivate",
                "actor": "0x1234...abcd",
                "target": "agent-42",
                "target_type": "agent",
                "before": {"active": True},
                "after": {"active": False},
                "ip_address": "192.168.1.100",
                "timestamp": "2026-05-18T08:00:00Z",
            }
        }

class AuditLogQuery(BaseModel):
    """Query parameters for filtering audit logs."""
    action: Optional[AuditAction] = None
    actor: Optional[str] = None
    target: Optional[str] = None
    target_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(50, le=200, ge=1)
    offset: int = Field(0, ge=0)
