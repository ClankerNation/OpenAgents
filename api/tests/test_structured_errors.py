import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app


def _register_test_routes() -> None:
    existing_paths = {route.path for route in app.router.routes}

    if "/__test/auth-failed" not in existing_paths:
        @app.get("/__test/auth-failed")
        async def _test_auth_failed():
            raise HTTPException(status_code=401, detail="Invalid token")

    if "/__test/rate-limited" not in existing_paths:
        @app.get("/__test/rate-limited")
        async def _test_rate_limited():
            raise HTTPException(
                status_code=429,
                detail={"message": "Rate limit exceeded", "retry_after": 12},
            )

    if "/__test/internal-error" not in existing_paths:
        @app.get("/__test/internal-error")
        async def _test_internal_error():
            raise RuntimeError("boom")


_register_test_routes()


class StructuredErrorResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def _assert_error_schema(self, response, expected_code: str):
        body = response.json()
        self.assertEqual(body["code"], expected_code)
        self.assertIsInstance(body["message"], str)
        self.assertIsInstance(body["details"], dict)
        self.assertIsInstance(body["request_id"], str)
        self.assertTrue(body["request_id"])
        self.assertEqual(response.headers.get("X-Request-ID"), body["request_id"])
        return body

    def test_not_found_error_code(self):
        response = self.client.get("/agents/missing-agent")
        self.assertEqual(response.status_code, 404)
        self._assert_error_schema(response, "NOT_FOUND")

    def test_validation_error_includes_field_details(self):
        response = self.client.get("/tasks/not-an-int")
        self.assertEqual(response.status_code, 422)
        body = self._assert_error_schema(response, "VALIDATION_ERROR")
        fields = body["details"].get("fields", [])
        self.assertTrue(any(item.get("field") == "task_id" for item in fields))
        self.assertTrue(any(item.get("location") == "path" for item in fields))

    def test_auth_failed_error_code(self):
        response = self.client.get("/__test/auth-failed")
        self.assertEqual(response.status_code, 401)
        self._assert_error_schema(response, "AUTH_FAILED")

    def test_rate_limited_error_code(self):
        response = self.client.get("/__test/rate-limited")
        self.assertEqual(response.status_code, 429)
        body = self._assert_error_schema(response, "RATE_LIMITED")
        self.assertEqual(body["details"].get("retry_after"), 12)

    def test_internal_error_code(self):
        response = self.client.get("/__test/internal-error")
        self.assertEqual(response.status_code, 500)
        body = self._assert_error_schema(response, "INTERNAL_ERROR")
        self.assertEqual(body["details"].get("error_type"), "RuntimeError")


if __name__ == "__main__":
    unittest.main()
