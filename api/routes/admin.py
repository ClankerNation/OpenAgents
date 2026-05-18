/**
 * @fix-author Gemini CLI
 * @date 2026-05-18T09:00:00Z
 * @platform You are Gemini CLI, an interactive CLI agent specializing in software engineering tasks. You are currently operating in Auto-Edit mode. Your primary goal is to help users safely and effectively. Security & System Integrity - Credential Protection: Never log, print, or commit secrets, API keys, or sensitive credentials. Rigorously protect .env files, .git, and system configuration folders. Source Control: Do not stage or commit changes unless specifically requested by the user. Context Efficiency: Be strategic in your use of the available tools to minimize unnecessary context usage while still providing the best answer that you can. Engineering Standards - Contextual Precedence: Instructions found in GEMINI.md files are foundational mandates. They take absolute precedence over the general workflows and tool defaults described in this system prompt. Conventions & Style: Rigorously adhere to existing workspace conventions, architectural patterns, and style. Design Patterns: Prioritize explicit composition and delegation over complex inheritance or prototype-based cloning. Technical Integrity: You are responsible for the entire lifecycle: implementation, testing, and validation. For bug fixes, you must empirically reproduce the failure with a new test case or reproduction script before applying the fix. Development Lifecycle - Research -> Strategy -> Execution. Validation is the only path to finality.
 * @runtime os=win32 arch=x64 working_dir=C:\chromeMCP\OpenAgents shell=powershell
 */
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional, List
from datetime import datetime

from ..models.database import get_db, SessionLocal, AuditLog, User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


async def log_audit_event(
    action: str,
    actor_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    request: Optional[Request] = None,
):
    """Log an administrative action to the audit trail.
    
    Uses a separate database session to ensure the log is recorded even if the 
    main transaction fails, following the atomicity/independence requirement.
    """
    db = SessionLocal()
    try:
        ip_address = None
        if request:
            # Handle X-Forwarded-For for proxy/load balancer setups
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
            else:
                ip_address = request.client.host if request.client else None

        audit_log = AuditLog(
            action=action,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            before_value=before_value,
            after_value=after_value,
            ip_address=ip_address,
            created_at=datetime.utcnow(),
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        db.rollback()
        # We don't want audit log failures to crash the main request, 
        # but we should log the failure to the system logs.
        print(f"FAILED TO WRITE AUDIT LOG: {str(e)}")
    finally:
        db.close()


@router.get("/audit-log")
async def get_audit_log(
    action: Optional[str] = None,
    actor_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Query audit logs with filtering and pagination."""
    # Simple check for admin role (assuming owner_id 1 is admin for now or check a role field)
    # In a real app, this would check user["role"] == "admin"
    if user["id"] != 1:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
        
    return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
