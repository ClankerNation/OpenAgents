"""Tests for payment endpoints including expired escrow processing."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

os.environ["JWT_SECRET"] = "test-secret-key"

from api.routes.payments import process_expired_escrows, ESCROW_GRACE_PERIOD_DAYS


class MockPayment:
    def __init__(self, id, status, amount, from_address, created_at):
        self.id = id
        self.status = status
        self.amount = amount
        self.from_address = from_address
        self.created_at = created_at
        self.to_address = None
        self.claimed_at = None


class MockQuery:
    def __init__(self, payments):
        self.payments = list(payments)
        self._cutoff = None

    def filter(self, *args):
        filtered = []
        for p in self.payments:
            if p.status == "escrowed":
                if self._cutoff is None or p.created_at < self._cutoff:
                    filtered.append(p)
        self.payments = filtered
        return self

    def all(self):
        return self.payments


class MockDB:
    def __init__(self, payments):
        self._payments = payments
        self.committed = False

    def query(self, model):
        return MockQuery(self._payments)

    def commit(self):
        self.committed = True


class TestProcessExpiredEscrows:
    def test_no_expired_escrows(self):
        db = MockDB([])
        user = {"id": "user1", "address": "0x123"}

        import asyncio
        result = asyncio.run(process_expired_escrows(user=user, db=db))

        assert result["processed"] == 0
        assert "No expired escrows" in result["message"]

    def test_expired_escrow_refunded(self):
        old_date = datetime.utcnow() - timedelta(days=60)
        payment = MockPayment(
            id=1,
            status="escrowed",
            amount=100.0,
            from_address="0xcreator",
            created_at=old_date,
        )
        db = MockDB([payment])
        user = {"id": "user1", "address": "0x123"}

        import asyncio
        result = asyncio.run(process_expired_escrows(user=user, db=db))

        assert result["processed"] == 1
        assert payment.status == "refunded"
        assert payment.to_address == "0xcreator"
        assert db.committed is True

    def test_recent_escrow_not_refunded(self):
        recent_date = datetime.utcnow() - timedelta(days=5)
        payment = MockPayment(
            id=2,
            status="escrowed",
            amount=50.0,
            from_address="0xcreator",
            created_at=recent_date,
        )
        db = MockDB([payment])
        user = {"id": "user1", "address": "0x123"}

        import asyncio
        result = asyncio.run(process_expired_escrows(user=user, db=db))

        assert result["processed"] == 0
        assert payment.status == "escrowed"

    def test_multiple_expired_refunded(self):
        old1 = datetime.utcnow() - timedelta(days=45)
        old2 = datetime.utcnow() - timedelta(days=90)
        payments = [
            MockPayment(1, "escrowed", 100.0, "0xa", old1),
            MockPayment(2, "escrowed", 200.0, "0xb", old2),
            MockPayment(3, "escrowed", 50.0, "0xc", datetime.utcnow() - timedelta(days=2)),
        ]
        db = MockDB(payments)
        user = {"id": "user1", "address": "0x123"}

        import asyncio
        result = asyncio.run(process_expired_escrows(user=user, db=db))

        assert result["processed"] == 2
        assert payments[0].status == "refunded"
        assert payments[1].status == "refunded"
        assert payments[2].status == "escrowed"

    def test_already_claimed_not_affected(self):
        payment = MockPayment(
            id=4,
            status="claimed",
            amount=75.0,
            from_address="0xcreator",
            created_at=datetime.utcnow() - timedelta(days=60),
        )
        db = MockDB([payment])
        user = {"id": "user1", "address": "0x123"}

        import asyncio
        result = asyncio.run(process_expired_escrows(user=user, db=db))

        assert result["processed"] == 0
        assert payment.status == "claimed"

    def test_grace_period_constant(self):
        assert ESCROW_GRACE_PERIOD_DAYS == 30
