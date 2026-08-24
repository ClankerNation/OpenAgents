"""
payments.py — Payments & escrow endpoints (fix for #197).

Implements:
  * POST /payments/process-expired  — auto-refund of escrows locked beyond
                                      the 30-day grace period.
  * amount > 0 validation on EscrowDeposit (rejects negative/zero deposits).
  * Row-level locking (SELECT ... FOR UPDATE) in claim and refund paths.
  * Timezone-aware datetimes everywhere.
  * Structured logging of every auto-refund (payment_id, task_id, amount,
    recipient).
  * Contributor traceability via the X-Contributor-Id header.
"""

from __future__ import annotations

import enum
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Numeric,
    String,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

logger = logging.getLogger("app.payments")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GRACE_PERIOD_DAYS = 30
ESCROW_GRACE_PERIOD = timedelta(days=GRACE_PERIOD_DAYS)
CONTRIBUTOR_HEADER = "X-Contributor-Id"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openagents.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (never naive)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EscrowStatus(str, enum.Enum):
    LOCKED = "locked"
    CLAIMED = "claimed"
    REFUNDED = "refunded"


class Escrow(Base):
    __tablename__ = "escrows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    depositor: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 6))
    status: Mapped[EscrowStatus] = mapped_column(
        SQLEnum(EscrowStatus), default=EscrowStatus.LOCKED, index=True
    )
    claimant: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refund_recipient: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )


class RefundRecord(Base):
    """Audit trail for every refund, manual or automatic."""

    __tablename__ = "refund_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 6))
    recipient: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    initiated_by: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EscrowDeposit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    depositor: str = Field(min_length=1)
    amount: Decimal = Field(
        gt=0, description="Escrow amount; must be strictly positive."
    )


class ClaimRequest(BaseModel):
    claimant: str = Field(min_length=1)


class RefundRequest(BaseModel):
    recipient: Optional[str] = Field(
        default=None,
        description="Refund destination; defaults to the original depositor.",
    )


class EscrowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    task_id: str
    depositor: str
    amount: Decimal
    status: EscrowStatus
    claimant: Optional[str] = None
    locked_at: datetime
    claimed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    refund_recipient: Optional[str] = None


class RefundedEscrow(BaseModel):
    payment_id: str
    task_id: str
    amount: Decimal
    recipient: str


class ProcessExpiredResponse(BaseModel):
    processed: int
    refunded: int
    total_refunded_amount: Decimal
    refunded_escrows: List[RefundedEscrow]
    errors: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lock_escrow(db: Session, payment_id: str) -> Escrow:
    """Fetch an escrow with a row-level lock (SELECT ... FOR UPDATE)."""
    escrow = db.execute(
        select(Escrow)
        .where(Escrow.payment_id == payment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    return escrow


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/deposit", response_model=EscrowOut, status_code=201)
def deposit_escrow(
    payload: EscrowDeposit,
    response: Response,
    db: Session = Depends(get_db),
    x_contributor_id: Annotated[
        Optional[str], Header(alias=CONTRIBUTOR_HEADER)
    ] = None,
):
    existing = db.execute(
        select(Escrow).where(Escrow.payment_id == payload.payment_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Escrow already exists for this payment_id",
        )

    escrow = Escrow(
        payment_id=payload.payment_id,
        task_id=payload.task_id,
        depositor=payload.depositor,
        amount=payload.amount,
        status=EscrowStatus.LOCKED,
        locked_at=utcnow(),
    )
    db.add(escrow)
    db.commit()
    db.refresh(escrow)

    if x_contributor_id:
        response.headers[CONTRIBUTOR_HEADER] = x_contributor_id
    logger.info(
        "escrow_deposited payment_id=%s task_id=%s amount=%s depositor=%s contributor=%s",
        escrow.payment_id,
        escrow.task_id,
        escrow.amount,
        escrow.depositor,
        x_contributor_id or "-",
    )
    return escrow


@router.post("/{payment_id}/claim", response_model=EscrowOut)
def claim_escrow(
    payment_id: str,
    payload: ClaimRequest,
    response: Response,
    db: Session = Depends(get_db),
    x_contributor_id: Annotated[
        Optional[str], Header(alias=CONTRIBUTOR_HEADER)
    ] = None,
):
    escrow = _lock_escrow(db, payment_id)
    if escrow.status != EscrowStatus.LOCKED:
        raise HTTPException(
            status_code=409,
            detail=f"Escrow cannot be claimed in state '{escrow.status.value}'",
        )

    escrow.status = EscrowStatus.CLAIMED
    escrow.claimant = payload.claimant
    escrow.claimed_at = utcnow()
    db.commit()
    db.refresh(escrow)

    if x_contributor_id:
        response.headers[CONTRIBUTOR_HEADER] = x_contributor_id
    logger.info(
        "escrow_claimed payment_id=%s task_id=%s claimant=%s contributor=%s",
        escrow.payment_id,
        escrow.task_id,
        escrow.claimant,
        x_contributor_id or "-",
    )
    return escrow


@router.post("/{payment_id}/refund", response_model=EscrowOut)
def refund_escrow(
    payment_id: str,
    payload: RefundRequest,
    response: Response,
    db: Session = Depends(get_db),
    x_contributor_id: Annotated[
        Optional[str], Header(alias=CONTRIBUTOR_HEADER)
    ] = None,
):
    escrow = _lock_escrow(db, payment_id)
    if escrow.status != EscrowStatus.LOCKED:
        raise HTTPException(
            status_code=409,
            detail=f"Escrow cannot be refunded in state '{escrow.status.value}'",
        )

    now = utcnow()
    recipient = payload.recipient or escrow.depositor
    escrow.status = EscrowStatus.REFUNDED
    escrow.refunded_at = now
    escrow.refund_recipient = recipient
    db.add(
        RefundRecord(
            payment_id=escrow.payment_id,
            task_id=escrow.task_id,
            amount=escrow.amount,
            recipient=recipient,
            processed_at=now,
            initiated_by=x_contributor_id or "manual-refund",
        )
    )
    db.commit()
    db.refresh(escrow)

    if x_contributor_id:
        response.headers[CONTRIBUTOR_HEADER] = x_contributor_id
    logger.info(
        "manual_refund payment_id=%s task_id=%s amount=%s recipient=%s contributor=%s",
        escrow.payment_id,
        escrow.task_id,
        escrow.amount,
        recipient,
        x_contributor_id or "-",
    )
    return escrow


@router.post("/process-expired", response_model=ProcessExpiredResponse)
def process_expired_escrows(
    response: Response,
    db: Session = Depends(get_db),
    x_contributor_id: Annotated[
        Optional[str], Header(alias=CONTRIBUTOR_HEADER)
    ] = None,
):
    """Refund every escrow still locked beyond the 30-day grace period.

    Idempotent: only rows in the LOCKED state are selected, and each row is
    re-checked under a row-level lock before the refund is committed, so a
    concurrent /claim can never race with the auto-refund.
    """
    now = utcnow()
    cutoff = now - ESCROW_GRACE_PERIOD

    expired = (
        db.execute(
            select(Escrow)
            .where(
                Escrow.status == EscrowStatus.LOCKED,
                Escrow.locked_at <= cutoff,
            )
            .order_by(Escrow.locked_at)
            .with_for_update()
        )
        .scalars()
        .all()
    )

    refunded_items: List[RefundedEscrow] = []
    errors: List[str] = []
    total_refunded = Decimal("0")

    for escrow in expired:
        try:
            # Re-check state under the row lock in case a concurrent claim
            # changed it between the select and this point.
            if escrow.status != EscrowStatus.LOCKED:
                continue

            recipient = escrow.depositor
            escrow.status = EscrowStatus.REFUNDED
            escrow.refunded_at = now
            escrow.refund_recipient = recipient
            db.add(
                RefundRecord(
                    payment_id=escrow.payment_id,
                    task_id=escrow.task_id,
                    amount=escrow.amount,
                    recipient=recipient,
                    processed_at=now,
                    initiated_by=x_contributor_id or "auto-refund-job",
                )
            )
            db.commit()

            total_refunded += escrow.amount
            refunded_items.append(
                RefundedEscrow(
                    payment_id=escrow.payment_id,
                    task_id=escrow.task_id,
                    amount=escrow.amount,
                    recipient=recipient,
                )
            )
            logger.info(
                "auto_refund payment_id=%s task_id=%s amount=%s recipient=%s locked_at=%s contributor=%s",
                escrow.payment_id,
                escrow.task_id,
                escrow.amount,
                recipient,
                escrow.locked_at.isoformat(),
                x_contributor_id or "-",
            )
        except Exception as exc:  # keep processing the rest of the batch
            db.rollback()
            logger.exception(
                "auto_refund_failed payment_id=%s", escrow.payment_id
            )
            errors.append(f"{escrow.payment_id}: {exc}")

    if x_contributor_id:
        response.headers[CONTRIBUTOR_HEADER] = x_contributor_id

    return ProcessExpiredResponse(
        processed=len(expired),
        refunded=len(refunded_items),
        total_refunded_amount=total_refunded,
        refunded_escrows=refunded_items,
        errors=errors,
    )


Base.metadata.create_all(bind=engine)