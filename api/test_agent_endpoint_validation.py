import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException

from api.validation.agent_endpoint import validate_agent_endpoint


class AgentEndpointValidationTest(unittest.IsolatedAsyncioTestCase):
    async def test_valid_url_passes_after_successful_head(self):
        response = Mock(status_code=204)
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.head.return_value = response

        with (
            patch(
                "api.validation.agent_endpoint._resolved_addresses",
                new=AsyncMock(return_value={"93.184.216.34"}),
            ),
            patch("api.validation.agent_endpoint.httpx.AsyncClient", return_value=client),
        ):
            endpoint = await validate_agent_endpoint("https://agent.example.com/health")

        self.assertEqual(endpoint, "https://agent.example.com/health")
        client.head.assert_awaited_once_with("https://agent.example.com/health")

    async def test_invalid_url_format_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            await validate_agent_endpoint("ftp://agent.example.com")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("http or https", raised.exception.detail)

    async def test_private_ip_literal_is_rejected_before_head_request(self):
        with patch("api.validation.agent_endpoint.httpx.AsyncClient") as client_cls:
            with self.assertRaises(HTTPException) as raised:
                await validate_agent_endpoint("http://192.168.1.25:8080")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("private or internal", raised.exception.detail)
        client_cls.assert_not_called()

    async def test_private_dns_resolution_is_rejected(self):
        with (
            patch(
                "api.validation.agent_endpoint._resolved_addresses",
                new=AsyncMock(return_value={"10.0.0.8"}),
            ),
            patch("api.validation.agent_endpoint.httpx.AsyncClient") as client_cls,
        ):
            with self.assertRaises(HTTPException) as raised:
                await validate_agent_endpoint("https://agent.example.com")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("private or internal", raised.exception.detail)
        client_cls.assert_not_called()

    async def test_timeout_returns_gateway_timeout(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.head.side_effect = httpx.TimeoutException("slow")

        with (
            patch(
                "api.validation.agent_endpoint._resolved_addresses",
                new=AsyncMock(return_value={"93.184.216.34"}),
            ),
            patch("api.validation.agent_endpoint.httpx.AsyncClient", return_value=client),
        ):
            with self.assertRaises(HTTPException) as raised:
                await validate_agent_endpoint("https://agent.example.com")

        self.assertEqual(raised.exception.status_code, 504)
        self.assertIn("timed out", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
