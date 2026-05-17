"""Tests for structured error responses (#202)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import unittest
from unittest.mock import MagicMock
from exceptions import (
    ErrorCode, error_response, get_request_id,
    register_exception_handlers
)


class TestErrorResponse(unittest.TestCase):
    def test_returns_correct_schema(self):
        r = error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="bad input",
            request_id="req-123",
            details={"field": "amount"},
            status_code=422,
        )
        body = r.body.decode()
        import json
        body_json = json.loads(body)
        self.assertEqual(body_json["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(body_json["message"], "bad input")
        self.assertEqual(body_json["request_id"], "req-123")
        self.assertEqual(body_json["details"]["field"], "amount")
        self.assertEqual(r.status_code, 422)
        print("✓ error_response schema correct")

    def test_get_request_id_generates_uuid(self):
        req = MagicMock()
        req.headers = {}
        rid = get_request_id(req)
        self.assertEqual(len(rid), 36)  # UUID v4 length
        print("✓ get_request_id generates UUID")

    def test_get_request_id_reads_header(self):
        req = MagicMock()
        req.headers = {"X-Request-ID": "existing-id"}
        self.assertEqual(get_request_id(req), "existing-id")
        print("✓ get_request_id reads header")


class TestErrorCodes(unittest.TestCase):
    def test_all_codes_defined(self):
        self.assertEqual(ErrorCode.VALIDATION_ERROR, "VALIDATION_ERROR")
        self.assertEqual(ErrorCode.NOT_FOUND, "NOT_FOUND")
        self.assertEqual(ErrorCode.AUTH_FAILED, "AUTH_FAILED")
        self.assertEqual(ErrorCode.RATE_LIMITED, "RATE_LIMITED")
        self.assertEqual(ErrorCode.INTERNAL_ERROR, "INTERNAL_ERROR")
        print("✓ all error codes defined")


if __name__ == "__main__":
    unittest.main()
