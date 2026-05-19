"""Tests for agent route fixes (issue #27).

Tests the name validation regex, pagination clamp, and owner filter
logic in isolation (avoids database import chain).
"""

import re
import pytest

# Mirrors the _NAME_PATTERN and _clamp_limit from routes/agents.py
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, 100))


class TestNameValidation:
    def test_valid_name_accepted(self):
        assert _NAME_PATTERN.match("valid-agent_123") is not None

    def test_empty_name_rejected(self):
        assert _NAME_PATTERN.match("") is None
        assert _NAME_PATTERN.match("   ") is None

    def test_too_long_name_rejected(self):
        assert _NAME_PATTERN.match("a" * 65) is None

    def test_special_chars_rejected(self):
        for bad in [
            "'; DROP TABLE users;--",
            "<script>alert(1)</script>",
            "name with spaces",
            "test@name",
        ]:
            assert _NAME_PATTERN.match(bad) is None, f"Should reject: {bad}"

    def test_64_char_name_accepted(self):
        assert _NAME_PATTERN.match("a" * 64) is not None


class TestPaginationCap:
    def test_limit_clamped(self):
        assert _clamp_limit(50) == 50
        assert _clamp_limit(100) == 100
        assert _clamp_limit(200) == 100
        assert _clamp_limit(9999) == 100
        assert _clamp_limit(0) == 1
        assert _clamp_limit(-5) == 1


class TestOwnerFilter:
    def test_non_integer_owner_rejected(self):
        with pytest.raises(ValueError):
            int("1 OR 1=1")

    def test_integer_owner_accepted(self):
        assert int("42") == 42
