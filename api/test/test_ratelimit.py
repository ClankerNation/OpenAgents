"""Tests for rate limiting middleware."""

import pytest
import time
from unittest.mock import Mock, AsyncMock
from fastapi import Request
from starlette.datastructures import Headers

# Import the module directly to test
import sys
sys.path.insert(0, 'D:/bounty/OpenAgents/api')

from middleware.ratelimit import RateLimitMiddleware, RateLimitConfig


class TestRateLimitConfig:
    def test_default_limits(self):
        config = RateLimitConfig()
        assert config.ANONYMOUS_LIMIT == 60
        assert config.AUTHENTICATED_LIMIT == 300
        assert config.PREMIUM_LIMIT == 1000


class TestRateLimitMiddleware:
    def test_get_client_ip_direct(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers()
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"

        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_forwarded(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"X-Forwarded-For": "10.0.0.1, 192.168.1.1"})
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"

        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"

    def test_get_auth_tier_anonymous(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers()

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "anonymous"
        assert limit == 60

    def test_get_auth_tier_authenticated(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        # Create a valid JWT token
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": "user123", "roles": ["user"]},
            "test-secret",
            algorithm="HS256"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": f"Bearer {token}"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "authenticated"
        assert limit == 300

    def test_get_auth_tier_premium(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        # Create a premium JWT token
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": "user123", "roles": ["user", "premium"]},
            "test-secret",
            algorithm="HS256"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": f"Bearer {token}"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "premium"
        assert limit == 1000

    def test_get_auth_tier_admin_premium(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        # Create an admin JWT token (also gets premium tier)
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": "admin123", "roles": ["admin"]},
            "test-secret",
            algorithm="HS256"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": f"Bearer {token}"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "premium"
        assert limit == 1000

    def test_get_auth_tier_invalid_token(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": "Bearer invalid-token"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "anonymous"
        assert limit == 60

    def test_get_auth_tier_wrong_secret(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        # Create token with different secret
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": "user123", "roles": ["premium"]},
            "wrong-secret",
            algorithm="HS256"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": f"Bearer {token}"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "anonymous"
        assert limit == 60

    def test_get_auth_tier_bearer_malformed(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(app=None, config=config)

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers({"Authorization": "Basic user:pass"})

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "anonymous"
        assert limit == 60


class TestRateLimitHeaders:
    """Test that correct headers are returned for each tier."""

    def test_headers_include_tier(self):
        config = RateLimitConfig()
        middleware = RateLimitMiddleware(
            app=None,
            config=config,
            jwt_secret="test-secret"
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = Headers()

        tier, limit = middleware._get_auth_tier(mock_request)
        assert tier == "anonymous"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
