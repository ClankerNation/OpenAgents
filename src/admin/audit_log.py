# ---- FILE: app/database.py ---- (merge into existing module if present)
# Contributor traceability | Issue #192 | PR #5868 (rework)
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "OPENAGENTS_DATABASE_URL",
    os.getenv("DATABASE_URL", "sqlite:///./openagents.db"),
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- FILE: app/models/user.py ----
# Contributor traceability | Issue #192 | PR #5868 (rework)
# Fixes: address index (#192), timezone-aware datetimes (#192), cascade delete (#192)
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    # FIX #192: timezone-aware UTC replaces naive datetime.utcnow()
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(64), unique=True, nullable=True, index=True)
    # FIX #192: previously missing index
    address = Column(String(255), nullable=True, index=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    api_token = Column(String(128), unique=True, nullable=True, index=True)
    # FIX #192: timezone-aware defaults
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # FIX #192: deleting a user removes their agents
    agents = relationship(
        "Agent",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


# ---- FILE: app/models/agent.py ----
# Contributor traceability | Issue #192 | PR #5868 (rework)
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    owner = relationship("User", back_populates="agents")


# ---- FILE: app/models/audit_log.py ----
# Contributor traceability | Issue #192 | PR #5868 (rework)
# Immutable, append-only audit trail with composite indexes for filtering.
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, event
from sqlalchemy.orm import Session

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(64), nullable=False)
    actor_id = Column(Integer, nullable=False)
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(128), nullable=True)
    before = Column(Text, nullable=True)
    after = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    @staticmethod
    def _encode(payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if payload is None:
            return None
        return json.dumps(payload, default=str, sort_keys=True)

    @classmethod
    def record(
        cls,
        db: Session,
        *,
        action: str,
        actor_id: int,
        target_type: Optional[str] = None,
        target_id: Optional[Any] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> "AuditLog":
        entry = cls(
            action=action,
            actor_id=actor_id,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            before=cls._encode(before),
            after=cls._encode(after),
            ip_address=ip_address,
        )
        db.add(entry)
        db.flush()
        return entry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "actor_id": self.actor_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "before": json.loads(self.before) if self.before else None,
            "after": json.loads(self.after) if self.after else None,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@event.listens_for(AuditLog, "before_update")
def _audit_log_immutable_update(mapper, connection, target):
    raise ValueError("AuditLog entries are immutable; updates are not permitted.")


@event.listens_for(AuditLog, "before_delete")
def _audit_log_immutable_delete(mapper, connection, target):
    raise ValueError("AuditLog entries are immutable; deletes are not permitted.")


# ---- FILE: app/routes/admin.py ----
# Contributor traceability | Issue #192 | PR #5868 (rework)
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])

_bearer_scheme = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    # Hook point: swap for the project's existing auth layer if one exists.
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.api_token == credentials.credentials).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user


def _user_snapshot(user: User) -> Dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "address": user.address,
        "is_admin": user.is_admin,
    }


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    address: Optional[str] = None
    is_admin: Optional[bool] = None

    class Config:
        extra = "forbid"


@router.get("/audit-log")
def list_audit_log(
    actor: Optional[str] = Query(default=None, description="Actor user id or username"),
    action: Optional[str] = Query(default=None, max_length=64),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)

    if actor:
        if actor.isdigit():
            query = query.filter(AuditLog.actor_id == int(actor))
        else:
            query = query.join(User, User.id == AuditLog.actor_id).filter(User.username == actor)
    if action:
        query = query.filter(AuditLog.action == action)

    start = _ensure_aware(start_date)
    end = _ensure_aware(end_date)
    if start is not None:
        query = query.filter(AuditLog.created_at >= start)
    if end is not None:
        query = query.filter(AuditLog.created_at <= end)

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": [row.to_dict() for row in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.put("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields provided to update")

    before = _user_snapshot(user)
    for field, value in changes.items():
        setattr(user, field, value)
    user.updated_at = datetime.now(timezone.utc)

    AuditLog.record(
        db,
        action="user.update",
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
        before=before,
        after=_user_snapshot(user),
        ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return _user_snapshot(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins