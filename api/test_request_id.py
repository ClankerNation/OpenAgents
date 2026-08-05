import logging
import unittest
import uuid

from fastapi.testclient import TestClient

from api.main import app
from api.middleware.request_id import REQUEST_ID_HEADER


class CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class RequestIdMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_response_has_generated_request_id_header(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        request_id = response.headers.get(REQUEST_ID_HEADER)
        self.assertIsNotNone(request_id)
        uuid.UUID(request_id)

    def test_client_request_id_is_preserved(self):
        request_id = "external-trace-178"

        response = self.client.get("/health", headers={REQUEST_ID_HEADER: request_id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers[REQUEST_ID_HEADER], request_id)

    def test_generated_request_ids_are_unique_per_request(self):
        first = self.client.get("/health").headers[REQUEST_ID_HEADER]
        second = self.client.get("/health").headers[REQUEST_ID_HEADER]

        self.assertNotEqual(first, second)

    def test_request_id_is_attached_to_logs(self):
        request_id = "log-correlation-178"
        logger = logging.getLogger("openagents.request_id")
        previous_level = logger.level
        handler = CaptureHandler()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        try:
            response = self.client.get("/health", headers={REQUEST_ID_HEADER: request_id})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(
                record.getMessage() == "request completed"
                and getattr(record, "request_id", None) == request_id
                and getattr(record, "status_code", None) == 200
                for record in handler.records
            )
        )


if __name__ == "__main__":
    unittest.main()
