"""Tests for escrow auto-refund endpoints (bounty #197)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from api.routes.payments import ESCROW_EXPIRY_DAYS


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_payment(
    id: int,
    task_id: int,
    status: str = "escrowed",
    amount: float = 100.0,
    from_address: str = "0xAAAA",
    release_time: datetime | None = None,
):
    """Build a mock Payment object with the given attributes."""
    p = MagicMock()
    p.id = id
    p.task_id = task_id
    p.status = status
    p.amount = amount
    p.from_address = from_address
    p.release_time = release_time
    return p


def _make_db(all_returns: list, filter_returns: list):
    """Return a mock DB session pre-configured.

    - `query().filter().all()` returns `filter_returns` (used by
      process-expired and /expired).
    - `query().all()` returns `all_returns` (used by /history).
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = filter_returns
    db.query.return_value.all.return_value = all_returns
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("api.routes.payments.datetime")
def test_process_expired_refunds_old_escrow(mock_dt):
    """process-expired should refund escrows past release_time + 30 days."""
    from api.routes.payments import process_expired_escrows

    now = datetime(2026, 5, 17, 12, 0, 0)
    mock_dt.utcnow.return_value = now

    old_release = now - timedelta(days=ESCROW_EXPIRY_DAYS + 5)
    fresh_release = now - timedelta(days=5)

    old_payment = _make_payment(1, 10, status="escrowed", release_time=old_release)
    fresh_payment = _make_payment(2, 20, status="escrowed", release_time=fresh_release)

    db = _make_db(
        all_returns=[old_payment, fresh_payment],
        filter_returns=[old_payment],  # only the old one matches the filter
    )

    refunded = asyncio.run(process_expired_escrows(db=db))

    # only the old escrow is refunded
    assert len(refunded) == 1
    assert refunded[0].payment_id == 1
    assert old_payment.status == "refunded"
    assert fresh_payment.status == "escrowed"
    db.commit.assert_called_once()


def test_fresh_escrow_not_affected():
    """An escrow with release_time in the future should NOT be refunded."""
    from api.routes.payments import process_expired_escrows

    now = datetime.utcnow()
    future_release = now + timedelta(days=10)

    payment = _make_payment(1, 10, status="escrowed", release_time=future_release)
    db = _make_db(all_returns=[payment], filter_returns=[])

    refunded = asyncio.run(process_expired_escrows(db=db))

    assert len(refunded) == 0
    assert payment.status == "escrowed"


def test_expired_endpoint_lists_only_expired():
    """GET /payments/expired should only list escrows past their deadline."""
    from api.routes.payments import list_expired_escrows

    now = datetime.utcnow()
    old_release = now - timedelta(days=ESCROW_EXPIRY_DAYS + 10)
    fresh_release = now - timedelta(days=2)

    old = _make_payment(1, 10, status="escrowed", release_time=old_release)
    fresh = _make_payment(2, 20, status="escrowed", release_time=fresh_release)

    db = _make_db(
        all_returns=[old, fresh],
        filter_returns=[old],
    )

    result = asyncio.run(list_expired_escrows(db=db))

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["payment_id"] == 1
    assert result[0]["task_id"] == 10
