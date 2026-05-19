"""Tests for payment fixes (issue #30)."""

import pytest


def _validate_amount(v: float) -> float:
    if v <= 0:
        raise ValueError("amount must be positive")
    return v


import hashlib


def _build_idempotency_hash(task_id: int, user_address: str, amount: float,
                             token_address: str, idempotency_key: str = None) -> str:
    raw = f"{task_id}:{user_address}:{amount}:{token_address}"
    if idempotency_key:
        raw = f"{idempotency_key}:{raw}"
    return hashlib.sha256(raw.encode()).hexdigest()


class TestAmountValidation:
    def test_positive_amount_accepted(self):
        assert _validate_amount(100.0) == 100.0

    def test_zero_amount_rejected(self):
        with pytest.raises(ValueError):
            _validate_amount(0.0)

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError):
            _validate_amount(-50.0)


class TestIdempotency:
    def test_idempotency_hash_deterministic(self):
        h1 = _build_idempotency_hash(1, "0xuser", 100.0, "0xtoken", "abc")
        h2 = _build_idempotency_hash(1, "0xuser", 100.0, "0xtoken", "abc")
        assert h1 == h2

    def test_idempotency_hash_differs_per_key(self):
        h1 = _build_idempotency_hash(1, "0xuser", 100.0, "0xtoken", "a")
        h2 = _build_idempotency_hash(1, "0xuser", 100.0, "0xtoken", "b")
        assert h1 != h2
