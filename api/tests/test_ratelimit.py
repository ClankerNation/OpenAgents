import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware import ratelimit
from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware


def build_client(config: RateLimitConfig) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return TestClient(app)


class RateLimitMiddlewareTests(unittest.TestCase):
    def setUp(self):
        ratelimit._request_counts.clear()

    def test_default_tier_limits_are_exposed(self):
        client = build_client(RateLimitConfig())

        anon = client.get("/ping")
        self.assertEqual(anon.status_code, 200)
        self.assertEqual(anon.headers["X-RateLimit-Limit"], "60")

        auth = client.get("/ping", headers={"Authorization": "Bearer user-token"})
        self.assertEqual(auth.status_code, 200)
        self.assertEqual(auth.headers["X-RateLimit-Limit"], "300")

        premium = client.get(
            "/ping",
            headers={"X-API-Key": "premium-key", "X-API-Tier": "premium"},
        )
        self.assertEqual(premium.status_code, 200)
        self.assertEqual(premium.headers["X-RateLimit-Limit"], "1000")

    def test_each_tier_can_hit_429_and_has_required_headers(self):
        client = build_client(
            RateLimitConfig(
                requests_per_window=1,
                authenticated_requests_per_window=2,
                premium_requests_per_window=3,
            )
        )

        first_anon = client.get("/ping")
        self.assertEqual(first_anon.status_code, 200)
        self.assertIn("X-RateLimit-Remaining", first_anon.headers)
        self.assertIn("X-RateLimit-Limit", first_anon.headers)
        self.assertIn("X-RateLimit-Reset", first_anon.headers)
        blocked_anon = client.get("/ping")
        self.assertEqual(blocked_anon.status_code, 429)
        self.assertIn("Retry-After", blocked_anon.headers)

        auth_headers = {"Authorization": "Bearer auth-token"}
        self.assertEqual(client.get("/ping", headers=auth_headers).status_code, 200)
        self.assertEqual(client.get("/ping", headers=auth_headers).status_code, 200)
        blocked_auth = client.get("/ping", headers=auth_headers)
        self.assertEqual(blocked_auth.status_code, 429)
        self.assertIn("Retry-After", blocked_auth.headers)

        premium_headers = {"X-API-Key": "k-1", "X-API-Tier": "premium"}
        self.assertEqual(client.get("/ping", headers=premium_headers).status_code, 200)
        self.assertEqual(client.get("/ping", headers=premium_headers).status_code, 200)
        self.assertEqual(client.get("/ping", headers=premium_headers).status_code, 200)
        blocked_premium = client.get("/ping", headers=premium_headers)
        self.assertEqual(blocked_premium.status_code, 429)
        self.assertIn("Retry-After", blocked_premium.headers)

    def test_health_endpoint_includes_rate_limit_headers(self):
        client = build_client(RateLimitConfig())
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-RateLimit-Remaining", response.headers)
        self.assertIn("X-RateLimit-Limit", response.headers)
        self.assertIn("X-RateLimit-Reset", response.headers)


if __name__ == "__main__":
    unittest.main()
