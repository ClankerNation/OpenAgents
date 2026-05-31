import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from api.models.database import Payment


class TestPaymentExpiredAt:
    def test_expired_at_from_release_time(self):
        payment = Payment(
            release_time=datetime(2026, 1, 1),
            created_at=datetime(2025, 12, 1),
        )
        assert payment.expired_at == datetime(2026, 1, 31)

    def test_expired_at_falls_back_to_created_at(self):
        payment = Payment(
            release_time=None,
            created_at=datetime(2026, 5, 1),
        )
        assert payment.expired_at == datetime(2026, 5, 31)

    def test_expired_at_returns_none_when_no_base(self):
        payment = Payment(release_time=None, created_at=None)
        assert payment.expired_at is None


class TestProcessExpiredAPI:
    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        app = FastAPI()
        from api.routes.payments import router
        app.include_router(router)
        return app

    def test_process_expired_requires_auth(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/payments/process-expired")
        assert resp.status_code == 403

    def test_process_expired_empty_when_no_expired(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        with patch("api.routes.payments.get_db") as mock_db, \
             patch("api.routes.payments.get_current_user") as mock_user:
            mock_user.return_value = {"id": 1, "address": "0xabc", "roles": ["admin"]}
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = []
            resp = client.post("/payments/process-expired", headers={"Authorization": "Bearer test"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 0

    def test_process_expired_refunds_expired_escrows(self, app):
        from fastapi.testclient import TestClient
        now = datetime.utcnow()
        escrow = Payment(
            id=1,
            task_id=1,
            from_address="0xpayer",
            amount=100.0,
            status="escrowed",
            release_time=now - timedelta(days=31),
            created_at=now - timedelta(days=38),
        )
        fresh = Payment(
            id=2,
            task_id=2,
            from_address="0xpayer2",
            amount=200.0,
            status="escrowed",
            release_time=now - timedelta(days=5),
            created_at=now - timedelta(days=5),
        )
        client = TestClient(app)
        with patch("api.routes.payments.get_db") as mock_db, \
             patch("api.routes.payments.get_current_user") as mock_user:
            mock_user.return_value = {"id": 1, "address": "0xabc", "roles": ["admin"]}
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = [escrow]
            resp = client.post("/payments/process-expired", headers={"Authorization": "Bearer test"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 1
            assert data["refunds"][0]["escrow_id"] == 1
            assert escrow.status == "refunded"
            assert escrow.to_address == "0xpayer"
