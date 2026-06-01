"""Tests for API key authentication."""
import pytest
from unittest.mock import patch, MagicMock


def test_hash_api_key_deterministic():
    """Same key always produces same hash."""
    from api.middleware.auth import hash_api_key
    h1 = hash_api_key("test-key-123")
    h2 = hash_api_key("test-key-123")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_api_key_unique():
    """Different keys produce different hashes."""
    from api.middleware.auth import hash_api_key
    h1 = hash_api_key("key-a")
    h2 = hash_api_key("key-b")
    assert h1 != h2


def test_generate_and_authenticate_api_key():
    """Generated API key can authenticate."""
    from api.middleware.auth import generate_api_key, authenticate_api_key

    raw_key, key_hash = generate_api_key("user-1", "0x1234", ["admin"])
    assert raw_key.startswith("ok_")

    user = authenticate_api_key(raw_key)
    assert user is not None
    assert user["id"] == "user-1"
    assert user["address"] == "0x1234"
    assert "admin" in user["roles"]


def test_invalid_api_key_rejected():
    """Wrong API key returns None."""
    from api.middleware.auth import authenticate_api_key
    assert authenticate_api_key("bad-key") is None
    assert authenticate_api_key("") is None


def test_revoke_api_key():
    """Revoked key can no longer authenticate."""
    from api.middleware.auth import generate_api_key, authenticate_api_key, revoke_api_key

    raw_key, key_hash = generate_api_key("user-2", "0x5678", [])
    assert authenticate_api_key(raw_key) is not None

    assert revoke_api_key(key_hash) is True
    assert authenticate_api_key(raw_key) is None


def test_revoke_nonexistent_key():
    """Revoking non-existent key returns False."""
    from api.middleware.auth import revoke_api_key
    assert revoke_api_key("nonexistent-hash") is False


def test_decode_token_pins_algorithm():
    """JWT decode only accepts HS256, not 'none'."""
    from api.middleware.auth import decode_token
    import jwt

    # Token with 'none' algorithm should be rejected
    token = jwt.encode({"sub": "user"}, "secret", algorithm="none")
    with pytest.raises(Exception):
        decode_token(token)


def test_jwt_secret_has_fallback():
    """JWT_SECRET defaults instead of crashing."""
    from api.middleware.auth import JWT_SECRET
    assert JWT_SECRET is not None
    assert len(JWT_SECRET) > 0
