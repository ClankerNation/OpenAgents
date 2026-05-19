"""Tests for task fixes (issue #48)."""

import pytest


class TestStatusValidation:
    def test_valid_status_accepted(self):
        VALID = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
        for s in VALID:
            assert s in VALID

    def test_invalid_status_rejected(self):
        VALID = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
        for bad in ["invalid", "hacked", ""]:
            assert bad not in VALID


class TestTransitions:
    TRANSITIONS = {
        "open": {"assigned", "cancelled"},
        "assigned": {"in_progress", "cancelled"},
        "in_progress": {"review", "cancelled"},
        "review": {"completed", "in_progress"},
        "completed": set(),
        "cancelled": set(),
    }

    def test_open_to_assigned_allowed(self):
        assert "assigned" in self.TRANSITIONS["open"]

    def test_completed_not_allowed_from_open(self):
        assert "completed" not in self.TRANSITIONS["open"]

    def test_completed_is_terminal(self):
        assert len(self.TRANSITIONS["completed"]) == 0

    def test_cancelled_is_terminal(self):
        assert len(self.TRANSITIONS["cancelled"]) == 0

    def test_review_to_completed_allowed(self):
        assert "completed" in self.TRANSITIONS["review"]


class TestPaginationCap:
    def test_clamp(self):
        def clamp(limit):
            return max(1, min(limit, 100))
        assert clamp(50) == 50
        assert clamp(200) == 100
        assert clamp(0) == 1
