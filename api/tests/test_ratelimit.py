import unittest

from starlette.requests import Request
from starlette.responses import Response

from api.middleware import ratelimit
from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware


async def _noop_app(scope, receive, send):
    return None


class RateLimitMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ratelimit._request_counts.clear()

    def _build_request(self, path="/agents", headers=None, client_ip="127.0.0.1"):
        header_items = []
        for key, value in (headers or {}).items():
            header_items.append((key.lower().encode("latin-1"), value.encode("latin-1")))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("latin-1"),
            "query_string": b"",
            "headers": header_items,
            "client": (client_ip, 12345),
            "server": ("testserver", 80),
        }
        return Request(scope)

    async def _ok_response(self, _request):
        return Response("ok", status_code=200)

    async def test_limits_differ_by_request_auth_state(self):
        middleware = RateLimitMiddleware(
            _noop_app,
            RateLimitConfig(
                requests_per_window=None,
                anonymous_requests_per_window=60,
                authenticated_requests_per_window=300,
                premium_requests_per_window=1000,
            ),
        )

        anonymous = await middleware.dispatch(self._build_request(), self._ok_response)
        authenticated = await middleware.dispatch(
            self._build_request(headers={"Authorization": "Bearer test-token"}, client_ip="127.0.0.2"),
            self._ok_response,
        )
        premium = await middleware.dispatch(
            self._build_request(headers={"X-API-Key": "premium_demo"}, client_ip="127.0.0.3"),
            self._ok_response,
        )

        self.assertEqual("60", anonymous.headers["X-RateLimit-Limit"])
        self.assertEqual("300", authenticated.headers["X-RateLimit-Limit"])
        self.assertEqual("1000", premium.headers["X-RateLimit-Limit"])

    async def test_headers_present_and_429_contains_retry_after(self):
        middleware = RateLimitMiddleware(
            _noop_app,
            RateLimitConfig(
                requests_per_window=None,
                anonymous_requests_per_window=1,
                authenticated_requests_per_window=1,
                premium_requests_per_window=1,
            ),
        )

        first = await middleware.dispatch(self._build_request(), self._ok_response)
        second = await middleware.dispatch(self._build_request(), self._ok_response)

        self.assertEqual(200, first.status_code)
        self.assertIn("X-RateLimit-Limit", first.headers)
        self.assertIn("X-RateLimit-Remaining", first.headers)
        self.assertIn("X-RateLimit-Reset", first.headers)

        self.assertEqual(429, second.status_code)
        self.assertIn("Retry-After", second.headers)
        self.assertIn("X-RateLimit-Limit", second.headers)
        self.assertIn("X-RateLimit-Remaining", second.headers)
        self.assertIn("X-RateLimit-Reset", second.headers)

    async def test_legacy_single_limit_remains_compatible(self):
        middleware = RateLimitMiddleware(_noop_app, RateLimitConfig(requests_per_window=2))

        first = await middleware.dispatch(self._build_request(), self._ok_response)
        second = await middleware.dispatch(
            self._build_request(headers={"Authorization": "Bearer token"}, client_ip="127.0.0.8"),
            self._ok_response,
        )
        third = await middleware.dispatch(
            self._build_request(headers={"X-API-Key": "premium_key"}, client_ip="127.0.0.9"),
            self._ok_response,
        )

        self.assertEqual("2", first.headers["X-RateLimit-Limit"])
        self.assertEqual("2", second.headers["X-RateLimit-Limit"])
        self.assertEqual("2", third.headers["X-RateLimit-Limit"])


if __name__ == "__main__":
    unittest.main()
