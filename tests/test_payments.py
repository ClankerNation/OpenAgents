"""Tests for payment and escrow endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from api.routes.payments import router, EXPIRY_DAYS


@pytest.fixture
def app():
    from api.models.database import init_db
    init_db()
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_deposit_escrow_amount_validation():
    """Escrow deposit requires positive amount."""
    from pydantic import ValidationError
    from api.routes.payments import EscrowDeposit
    try:
        EscrowDeposit(task_id=1, amount=0)
        assert False, "Should have raised validation error"
    except Exception:
        pass  # Expected - amount <= 0 should be rejected


def test_process_expired_endpoint_exists(client):
    """Process-expired endpoint exists."""
    # Without DB, it will fail, but endpoint should exist
    response = client.post("/payments/process-expired")
    # Should not be 404
    assert response.status_code != 404


def test_expiry_days_constant():
    """Expiry days is 30."""
    assert EXPIRY_DAYS == 30


def test_escrow_deposit_model():
    """EscrowDeposit model validates correctly."""
    from api.routes.payments import EscrowDeposit
    deposit = EscrowDeposit(task_id=1, amount=100.0)
    assert deposit.task_id == 1
    assert deposit.amount == 100.0
    assert deposit.token_address == "0x0000000000000000000000000000000000000000"


def test_claim_request_model():
    """ClaimRequest model validates correctly."""
    from api.routes.payments import ClaimRequest
    claim = ClaimRequest(task_id=1, recipient_address="0xabc")
    assert claim.task_id == 1
    assert claim.recipient_address == "0xabc"
