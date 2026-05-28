import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


class RateLimitMiddlewareTests(unittest.TestCase):
    def setUp(self):
        _request_counts.clear()
        self.app = FastAPI()
        self.app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=60,
                authenticated_requests_per_window=300,
                premium_requests_per_window=1000,
                window_seconds=60,
            ),
        )

        @self.app.get("/resource")
        async def resource():
            return {"ok": True}

        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        self.client = TestClient(self.app)

    def _consume_window(self, path: str = "/resource", *, headers=None, count=1):
        responses = [self.client.get(path, headers=headers or {}) for _ in range(count)]
        return responses[-1]

    def test_anonymous_limit_headers(self):
        response = self.client.get("/resource")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-RateLimit-Limit"], "60")
        self.assertEqual(response.headers["X-RateLimit-Remaining"], "59")
        self.assertIn("X-RateLimit-Reset", response.headers)

    def test_authenticated_limit_headers(self):
        response = self.client.get("/resource", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-RateLimit-Limit"], "300")
        self.assertEqual(response.headers["X-RateLimit-Remaining"], "299")

    def test_premium_limit_headers(self):
        response = self.client.get(
            "/resource",
            headers={"X-API-Key": "premium_demo_key", "Authorization": "Bearer token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-RateLimit-Limit"], "1000")
        self.assertEqual(response.headers["X-RateLimit-Remaining"], "999")

    def test_429_includes_retry_after_and_limit_headers(self):
        with patch("middleware.ratelimit.time.time", return_value=1_000.0):
            response = self._consume_window(count=60)
            self.assertEqual(response.status_code, 200)
            limited = self.client.get("/resource")

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["X-RateLimit-Limit"], "60")
        self.assertEqual(limited.headers["X-RateLimit-Remaining"], "0")
        self.assertIn("X-RateLimit-Reset", limited.headers)
        self.assertIn("Retry-After", limited.headers)
        self.assertEqual(limited.json()["retry_after"], int(limited.headers["Retry-After"]))

    def test_health_path_is_not_rate_limited(self):
        responses = [self.client.get("/health") for _ in range(75)]
        self.assertTrue(all(response.status_code == 200 for response in responses))


if __name__ == "__main__":
    unittest.main()
