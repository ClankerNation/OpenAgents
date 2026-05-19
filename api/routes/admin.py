/**
 * @fix-author oocheol
 * @date 2026-05-19T06:45:00Z
 * @platform Gemini CLI engineering agent. Focus: Non-destructive, idiomatic code modifications, comprehensive testing, and secure credential handling. Follows Research-Strategy-Execution lifecycle.
 * @runtime os=win32, arch=x64, working_directory=C:\chromeMCP\OpenAgents, shell=powershell
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
        # Audit log failures shouldn't crash the main request but should be reported
        print(f"CRITICAL: FAILED TO WRITE AUDIT LOG: {str(e)}")
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
    # Strict admin check
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
