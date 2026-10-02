import asyncio
import time
from unittest.mock import patch, Mock

import pytest
from fastapi import Request, Response
from starlette.datastructures import Headers

import api.middleware.ratelimit as ratelimit
from api.middleware.ratelimit import RateLimiter, AUTH_LIMIT, ANON_LIMIT, WINDOW_SIZE


@pytest.fixture(autouse=True)
def reset_rate_limits():
    ratelimit._request_counts = {
        "auth": {},
        "anon": {}
    }


@pytest.fixture
def rate_limiter():
    return RateLimiter(app=None)


@pytest.fixture
def mock_request():
    request = Mock(spec=Request)
    request.url.path = "/test"
    request.client.host = "127.0.0.1"
    request.headers = Headers({})
    return request


@pytest.fixture
def mock_call_next():
    async def call_next(request):
        return Response(content="OK", status_code=200)
    return call_next


def test_anonymous_limit(rate_limiter, mock_request, mock_call_next):
    # Mock time to control window
    with patch('api.middleware.ratelimit.time') as mock_time:
        mock_time.time.return_value = 1000.0  # Fixed time

        # First 100 requests should pass
        for i in range(ANON_LIMIT):
            mock_request.headers = Headers({})  # No auth
            response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
            assert response.status_code == 200, f"Request {i+1} failed"
            assert int(response.headers["X-RateLimit-Remaining"]) == ANON_LIMIT - i - 1

        # 101st request should be rate limited
        mock_request.headers = Headers({})
        response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(WINDOW_SIZE)


def test_authenticated_limit(rate_limiter, mock_request, mock_call_next):
    # Mock time and auth
    with patch('api.middleware.ratelimit.time') as mock_time, \
         patch('api.middleware.ratelimit.decode_token') as mock_decode:
        mock_time.time.return_value = 1000.0
        mock_decode.return_value = {"sub": "user123"}

        # First 1000 authenticated requests should pass
        for i in range(AUTH_LIMIT):
            mock_request.headers = Headers({"Authorization": "Bearer validtoken"})
            response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
            assert response.status_code == 200, f"Request {i+1} failed"
            assert int(response.headers["X-RateLimit-Remaining"]) == AUTH_LIMIT - i - 1

        # 1001st request should be rate limited
        mock_request.headers = Headers({"Authorization": "Bearer validtoken"})
        response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(WINDOW_SIZE)


def test_health_endpoint_not_rate_limited(rate_limiter, mock_request, mock_call_next):
    mock_request.url.path = "/health"
    # Even with many requests, health should pass
    for i in range(10):
        response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
        assert response.status_code == 200


def test_rate_limit_headers(rate_limiter, mock_request, mock_call_next):
    with patch('api.middleware.ratelimit.time') as mock_time:
        mock_time.time.return_value = 1000.0

        mock_request.headers = Headers({})  # anonymous
        response = asyncio.run(rate_limiter.dispatch(mock_request, mock_call_next))
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == str(ANON_LIMIT)
        assert response.headers["X-RateLimit-Remaining"] == str(ANON_LIMIT - 1)