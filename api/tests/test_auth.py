"""Tests for hardened JWT auth middleware (issue #28).

Covers:
  - Algorithm 'none' is rejected
  - Graceful fallback when JWT_SECRET unset
  - Token revocation via jti blacklist
  - Normal token creation and decoding
"""

import os
import sys
import time
import pytest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from middleware.auth import (
    _resolve_jwt_secret,
    _token_blacklist,
    _clean_blacklist,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JWT_TEST_SECRET = "test-secret-for-unit-tests-32chars!"


@pytest.fixture(autouse=True)
def _patch_secret():
    """Force a known JWT secret for all tests."""
    with mock.patch("middleware.auth.JWT_SECRET", JWT_TEST_SECRET):
        _token_blacklist.clear()
        yield
        _token_blacklist.clear()


_SAMPLE_USER = {"sub": "user-1", "address": "0xabcd", "roles": []}


# ---------------------------------------------------------------------------
# Algorithm pinning
# ---------------------------------------------------------------------------

class TestAlgorithmPinned:
    def test_none_algorithm_rejected(self):
        """A token with alg=none must be rejected by decode_token."""
        import jwt as _jwt
        # Forge a token with alg=none
        none_token = _jwt.encode(
            {"sub": "attacker", "type": "access"},
            key="",
            algorithm="none",
        )
        with pytest.raises(Exception) as exc:
            decode_token(none_token)
        assert exc.value.status_code == 401

    def test_valid_hs256_token_accepted(self):
        token = create_access_token(_SAMPLE_USER)
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["type"] == "access"


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

class TestTokenTypes:
    def test_refresh_token_has_refresh_type(self):
        token = create_refresh_token(_SAMPLE_USER)
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_access_token_has_jti(self):
        token = create_access_token(_SAMPLE_USER)
        payload = decode_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) == 24  # 12 hex bytes


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

class TestTokenRevocation:
    def test_revoked_token_is_rejected(self):
        token = create_access_token(_SAMPLE_USER)
        import jwt as _jwt
        payload = _jwt.decode(
            token, JWT_TEST_SECRET, algorithms=[JWT_ALGORITHM]
        )
        jti = payload["jti"]
        revoke_token(jti, ttl_seconds=3600)
        with pytest.raises(Exception) as exc:
            decode_token(token)
        assert exc.value.status_code == 401

    def test_unrevoked_token_still_works(self):
        token = create_access_token(_SAMPLE_USER)
        payload = decode_token(token)
        assert payload["sub"] == "user-1"

    def test_blacklist_cleanup_removes_expired(self):
        _token_blacklist["expired-jti"] = time.time() - 10
        _token_blacklist["active-jti"] = time.time() + 3600
        _clean_blacklist()
        assert "expired-jti" not in _token_blacklist
        assert "active-jti" in _token_blacklist


# ---------------------------------------------------------------------------
# Secret fallback
# ---------------------------------------------------------------------------

class TestSecretFallback:
    def test_env_var_used_when_set(self):
        with mock.patch.dict(os.environ, {"JWT_SECRET": "env-secret"}):
            assert _resolve_jwt_secret() == "env-secret"

    def test_fallback_generated_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.warns(RuntimeWarning, match="JWT_SECRET not set"):
                secret = _resolve_jwt_secret()
            assert len(secret) == 64  # SHA-256 hex
            # Each call generates a fresh fallback (security-by-design:
            # prevents deterministic secrets across process restarts)
            with pytest.warns(RuntimeWarning):
                secret2 = _resolve_jwt_secret()
            assert len(secret2) == 64
            # Different calls produce different values (no persistence)
            assert secret != secret2
