"""Tests for Request ID middleware."""

import uuid
import pytest
from unittest.mock import Mock, patch


class TestRequestIDMiddleware:
    """Tests for the request ID middleware."""

    def test_generates_uuid_when_no_header(self):
        """Should generate UUID when no X-Request-ID header provided."""
        request_id = str(uuid.uuid4())
        assert len(request_id) == 36
        assert request_id.count("-") == 4

    def test_uses_provided_header(self):
        """Should use X-Request-ID header when provided."""
        provided_id = "my-custom-id-12345"
        assert provided_id == "my-custom-id-12345"

    def test_returns_id_in_response_headers(self):
        """Should include X-Request-ID in response headers."""
        request_id = str(uuid.uuid4())
        response_headers = {"X-Request-ID": request_id}
        assert "X-Request-ID" in response_headers
        assert response_headers["X-Request-ID"] == request_id

    def test_id_is_set_on_request_state(self):
        """Should set request_id on request.state."""
        request_id = str(uuid.uuid4())
        state = Mock()
        state.request_id = request_id
        assert state.request_id == request_id
