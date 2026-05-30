"""
Tests for structured error responses (Issue #202).

Every test verifies that the API returns errors in the canonical shape:

    {
        "error": {
            "code": "<ErrorCode>",
            "message": "<string>",
            "details": { ... },
            "request_id": "<string>"
        }
    }

Coverage:
  - VALIDATION_ERROR (422) — missing / invalid fields
  - NOT_FOUND (404) — unknown resource IDs
  - AUTH_FAILED (401) — missing / invalid / expired tokens
  - FORBIDDEN (403) — insufficient permissions
  - RATE_LIMITED (429) — rate limit exceeded
  - BAD_REQUEST (400) — invalid state transitions
  - INTERNAL_ERROR (500) — unhandled exceptions
  - Request-ID presence on every response
"""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set JWT_SECRET before importing anything from the app
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")

from api.main import app
from api.errors import APIError, ErrorCode, register_error_handlers, _build_error_response
from api.middleware.auth import create_access_token, generate_login_tokens, create_refresh_token
from api.middleware import ratelimit as ratelimit_module
from api.models.database import get_db, Base, Agent, Task


# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_structured_errors.db"
test_engine = create_engine(TEST_DB_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Register the dependency override once
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create all tables in the test DB."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    try:
        os.remove("./test_structured_errors.db")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_state():
    """Clear in-memory caches and rate limiter state before each test."""
    from api.main import agents_cache, tasks_cache
    agents_cache.clear()
    tasks_cache.clear()
    ratelimit_module._request_counts.clear()
    yield


@pytest.fixture
def client():
    """Create a TestClient."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    """Return headers with a valid access token for user-1."""
    token = create_access_token({
        "sub": "user-1",
        "address": "0xabc123",
        "roles": ["user"],
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_agent():
    """Create a test agent in the DB owned by user-1 and return it."""
    db = TestSessionLocal()
    try:
        agent = Agent(
            name="test-agent",
            description="A test agent",
            model_type="gpt-4",
            config={},
            owner_id="user-1",
            created_at=datetime.utcnow(),
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
    finally:
        db.close()


@pytest.fixture
def seed_other_agent():
    """Create a test agent owned by user-999 (a different user)."""
    db = TestSessionLocal()
    try:
        agent = Agent(
            name="other-agent",
            description="Not ours",
            model_type="gpt-4",
            config={},
            owner_id="user-999",
            created_at=datetime.utcnow(),
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
    finally:
        db.close()


@pytest.fixture
def seed_task():
    """Create a test task in the DB owned by user-1."""
    db = TestSessionLocal()
    try:
        task = Task(
            title="Test task",
            description="A test task",
            reward_amount=100.0,
            creator_id="user-1",
            status="open",
            created_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task
    finally:
        db.close()


@pytest.fixture
def seed_active_task():
    """Create a task with status 'in_progress' owned by user-1."""
    db = TestSessionLocal()
    try:
        task = Task(
            title="Active task",
            description="In progress task",
            reward_amount=200.0,
            creator_id="user-1",
            status="in_progress",
            created_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task
    finally:
        db.close()


def _assert_error_shape(body: dict, expected_code: str):
    """Assert the response body conforms to the structured error schema."""
    assert "error" in body, f"Missing 'error' key in {body}"
    error = body["error"]
    assert "code" in error, f"Missing 'code' in {error}"
    assert "message" in error, f"Missing 'message' in {error}"
    assert "details" in error, f"Missing 'details' in {error}"
    assert "request_id" in error, f"Missing 'request_id' in {error}"
    assert error["code"] == expected_code, f"Expected code={expected_code}, got {error['code']}"
    assert isinstance(error["message"], str), "message must be a string"
    assert isinstance(error["details"], dict), "details must be a dict"
    assert isinstance(error["request_id"], str), "request_id must be a string"
    assert len(error["request_id"]) > 0, "request_id must not be empty"


# ---------------------------------------------------------------------------
# VALIDATION_ERROR (422)
# ---------------------------------------------------------------------------

class TestValidationError:
    """Test that Pydantic validation errors produce VALIDATION_ERROR with
    field-level details."""

    def test_missing_required_field_agent_create(self, client, auth_headers):
        """POST /agents without 'name' should return VALIDATION_ERROR."""
        resp = client.post("/agents/", json={}, headers=auth_headers)
        assert resp.status_code == 422
        body = resp.json()
        _assert_error_shape(body, "VALIDATION_ERROR")
        assert "fields" in body["error"]["details"]

    def test_invalid_query_param_type(self, client):
        """GET /agents with invalid limit type should return VALIDATION_ERROR."""
        resp = client.get("/agents", params={"limit": "not_a_number"})
        assert resp.status_code == 422
        body = resp.json()
        _assert_error_shape(body, "VALIDATION_ERROR")
        assert "fields" in body["error"]["details"]

    def test_validation_error_includes_field_paths(self, client, auth_headers):
        """Validation errors should include dotted field paths in details."""
        resp = client.post(
            "/tasks/",
            json={"title": "test"},  # missing description, reward_amount
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        _assert_error_shape(body, "VALIDATION_ERROR")
        fields = body["error"]["details"]["fields"]
        # Should mention the missing fields
        field_str = " ".join(fields.keys())
        assert "description" in field_str or "reward_amount" in field_str

    def test_validation_error_on_invalid_path_param(self, client):
        """GET /agents/not-a-string-id should work (agent_id is str in main.py)."""
        # But GET /tasks/not-an-int should fail
        resp = client.get("/tasks/not-an-int")
        assert resp.status_code == 422
        _assert_error_shape(resp.json(), "VALIDATION_ERROR")


# ---------------------------------------------------------------------------
# NOT_FOUND (404)
# ---------------------------------------------------------------------------

class TestNotFoundError:
    """Test that missing resources return NOT_FOUND."""

    def test_agent_not_found_in_memory(self, client):
        """GET /agents/99999 (in-memory endpoint) should return NOT_FOUND."""
        resp = client.get("/agents/99999")
        assert resp.status_code == 404
        body = resp.json()
        _assert_error_shape(body, "NOT_FOUND")

    def test_agent_not_found_db(self, client):
        """GET /agents/99999 should return NOT_FOUND (matched by in-memory route)."""
        resp = client.get("/agents/99999")
        assert resp.status_code == 404
        body = resp.json()
        _assert_error_shape(body, "NOT_FOUND")

    def test_task_not_found_in_memory(self, client):
        """GET /tasks/99999 (in-memory endpoint) should return NOT_FOUND."""
        resp = client.get("/tasks/99999")
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")

    def test_task_not_found_on_status_update(self, client, auth_headers):
        """PATCH /tasks/99999/status should return NOT_FOUND."""
        resp = client.patch(
            "/tasks/99999/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")
        assert "task_id" in resp.json()["error"]["details"]

    def test_agent_not_found_on_update(self, client, auth_headers):
        """PUT /agents/99999 should return NOT_FOUND."""
        resp = client.put(
            "/agents/99999",
            json={"name": "updated"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")
        assert "agent_id" in resp.json()["error"]["details"]

    def test_agent_not_found_on_delete(self, client):
        """DELETE /agents/99999 should return NOT_FOUND."""
        resp = client.delete("/agents/99999")
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")

    def test_task_not_found_on_cancel(self, client, auth_headers):
        """DELETE /tasks/99999 should return NOT_FOUND."""
        resp = client.delete("/tasks/99999", headers=auth_headers)
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")

    def test_payment_task_not_found(self, client, auth_headers):
        """POST /payments/escrow/deposit with nonexistent task should return NOT_FOUND."""
        resp = client.post(
            "/payments/escrow/deposit",
            json={"task_id": 99999, "amount": 10.0},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")

    def test_nonexistent_route_returns_not_found(self, client):
        """GET /nonexistent should return NOT_FOUND via the global handler."""
        resp = client.get("/this-endpoint-does-not-exist")
        assert resp.status_code == 404
        _assert_error_shape(resp.json(), "NOT_FOUND")


# ---------------------------------------------------------------------------
# AUTH_FAILED (401)
# ---------------------------------------------------------------------------

class TestAuthFailedError:
    """Test that authentication failures return AUTH_FAILED."""

    def test_missing_auth_header(self, client):
        """POST /agents/ without Authorization header should return AUTH_FAILED."""
        resp = client.post("/agents/", json={"name": "test"})
        assert resp.status_code == 401
        body = resp.json()
        _assert_error_shape(body, "AUTH_FAILED")

    def test_invalid_token(self, client):
        """A garbage token should return AUTH_FAILED."""
        resp = client.post(
            "/agents/",
            json={"name": "test"},
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401
        _assert_error_shape(resp.json(), "AUTH_FAILED")

    def test_expired_token(self, client):
        """An expired token should return AUTH_FAILED."""
        token = create_access_token(
            {"sub": "user-1", "address": "0xabc", "roles": []},
            expires_delta=timedelta(seconds=-1),
        )
        resp = client.post(
            "/agents/",
            json={"name": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        _assert_error_shape(body, "AUTH_FAILED")
        assert "expired" in body["error"]["message"].lower()

    def test_wrong_token_type(self, client):
        """A refresh token used as access should return AUTH_FAILED."""
        token = create_refresh_token({"sub": "user-1", "address": "0xabc", "roles": []})
        resp = client.post(
            "/agents/",
            json={"name": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        _assert_error_shape(body, "AUTH_FAILED")
        assert "type" in body["error"]["message"].lower()

    def test_auth_failed_includes_request_id(self, client):
        """AUTH_FAILED responses must include request_id."""
        resp = client.post(
            "/agents/",
            json={"name": "test"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        body = resp.json()
        assert body["error"]["request_id"] == resp.headers.get("X-Request-ID")


# ---------------------------------------------------------------------------
# FORBIDDEN (403)
# ---------------------------------------------------------------------------

class TestForbiddenError:
    """Test that authorization failures return FORBIDDEN."""

    def test_update_agent_not_owner(self, client, auth_headers, seed_other_agent):
        """Updating another user's agent should return FORBIDDEN."""
        resp = client.put(
            f"/agents/{seed_other_agent.id}",
            json={"name": "hacked"},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        body = resp.json()
        _assert_error_shape(body, "FORBIDDEN")
        assert "agent_id" in body["error"]["details"]

    def test_update_task_status_not_creator(self, client, seed_task):
        """Updating status on another user's task should return FORBIDDEN."""
        # Auth as user-2 (not the creator)
        token = create_access_token({
            "sub": "user-2",
            "address": "0xdef456",
            "roles": ["user"],
        })
        resp = client.patch(
            f"/tasks/{seed_task.id}/status",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        body = resp.json()
        _assert_error_shape(body, "FORBIDDEN")

    def test_cancel_task_not_creator(self, client, seed_task):
        """Cancelling another user's task should return FORBIDDEN."""
        token = create_access_token({
            "sub": "user-2",
            "address": "0xdef456",
            "roles": ["user"],
        })
        resp = client.delete(
            f"/tasks/{seed_task.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        _assert_error_shape(resp.json(), "FORBIDDEN")

    def test_escrow_deposit_not_creator(self, client, seed_task):
        """Depositing escrow for another user's task should return FORBIDDEN."""
        token = create_access_token({
            "sub": "user-2",
            "address": "0xdef456",
            "roles": ["user"],
        })
        resp = client.post(
            "/payments/escrow/deposit",
            json={"task_id": seed_task.id, "amount": 10.0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        _assert_error_shape(resp.json(), "FORBIDDEN")


# ---------------------------------------------------------------------------
# RATE_LIMITED (429)
# ---------------------------------------------------------------------------

class TestRateLimitedError:
    """Test that exceeding the rate limit returns RATE_LIMITED."""

    def test_rate_limit_exceeded(self, client):
        """Exceeding the rate limit should return RATE_LIMITED with retry_after."""
        # Manually set rate limit state to trigger limit for the testclient IP
        import time
        ratelimit_module._request_counts["testclient"] = (100, time.time())

        # /agents is not bypassed by the rate limiter (unlike /health)
        resp = client.get("/agents")
        assert resp.status_code == 429
        body = resp.json()
        _assert_error_shape(body, "RATE_LIMITED")
        assert "retry_after" in body["error"]["details"]
        assert "Retry-After" in resp.headers


# ---------------------------------------------------------------------------
# BAD_REQUEST (400)
# ---------------------------------------------------------------------------

class TestBadRequestError:
    """Test that invalid state transitions return BAD_REQUEST."""

    def test_cancel_active_task(self, client, auth_headers, seed_active_task):
        """Cancelling a non-open/assigned task should return BAD_REQUEST."""
        resp = client.delete(f"/tasks/{seed_active_task.id}", headers=auth_headers)
        assert resp.status_code == 400
        body = resp.json()
        _assert_error_shape(body, "BAD_REQUEST")
        assert "current_status" in body["error"]["details"]


# ---------------------------------------------------------------------------
# INTERNAL_ERROR (500)
# ---------------------------------------------------------------------------

class TestInternalError:
    """Test that unhandled exceptions return INTERNAL_ERROR."""

    def test_unhandled_exception_returns_500(self, client):
        """An unhandled exception should return INTERNAL_ERROR with safe message."""

        @app.get("/test-crash")
        async def crash():
            raise RuntimeError("Something went terribly wrong")

        try:
            resp = client.get("/test-crash")
            assert resp.status_code == 500
            body = resp.json()
            _assert_error_shape(body, "INTERNAL_ERROR")
            # Must not leak internal details
            assert "RuntimeError" not in body["error"]["message"]
            assert "terribly wrong" not in body["error"]["message"]
        finally:
            # Cleanup test route
            app.routes[:] = [r for r in app.routes if not hasattr(r, "path") or r.path != "/test-crash"]


# ---------------------------------------------------------------------------
# Request-ID
# ---------------------------------------------------------------------------

class TestRequestID:
    """Test that every response includes a request ID."""

    def test_request_id_on_success(self, client):
        """Successful responses should include X-Request-ID header."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_request_id_on_error(self, client):
        """Error responses should include request_id in body and header."""
        resp = client.get("/agents/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["request_id"] == resp.headers["X-Request-ID"]

    def test_client_can_supply_request_id(self, client):
        """If client sends X-Request-ID, it should be echoed back."""
        resp = client.get("/agents/99999", headers={"X-Request-ID": "my-req-123"})
        assert resp.headers["X-Request-ID"] == "my-req-123"
        assert resp.json()["error"]["request_id"] == "my-req-123"

    def test_request_id_on_validation_error(self, client):
        """Validation error responses should include request_id."""
        resp = client.get("/tasks/not-a-number")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["request_id"] is not None
        assert body["error"]["request_id"] == resp.headers["X-Request-ID"]

    def test_request_id_on_auth_error(self, client):
        """Auth error responses should include request_id."""
        resp = client.post("/agents/", json={"name": "x"})
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["request_id"] == resp.headers["X-Request-ID"]


# ---------------------------------------------------------------------------
# Error code mapping completeness
# ---------------------------------------------------------------------------

class TestErrorCodeMapping:
    """Verify all error codes are documented and map to correct HTTP statuses."""

    def test_all_codes_have_status_mapping(self):
        """Every ErrorCode should have a corresponding HTTP status code."""
        from api.errors import _CODE_TO_STATUS, ErrorCode
        for code in ErrorCode:
            assert code in _CODE_TO_STATUS, f"{code} missing from _CODE_TO_STATUS"

    def test_error_response_schema_fields(self):
        """ErrorResponse model should have exactly the required fields."""
        from api.errors import ErrorResponse, ErrorDetail

        error_detail_fields = set(ErrorDetail.model_fields.keys())
        assert error_detail_fields == {"code", "message", "details", "request_id"}

        error_response_fields = set(ErrorResponse.model_fields.keys())
        assert error_response_fields == {"error"}

    def test_all_error_codes_in_enum(self):
        """Verify all required error codes exist in the enum."""
        required = {
            "VALIDATION_ERROR", "NOT_FOUND", "AUTH_FAILED",
            "RATE_LIMITED", "INTERNAL_ERROR",
        }
        actual = {e.value for e in ErrorCode}
        assert required.issubset(actual), f"Missing codes: {required - actual}"


# ---------------------------------------------------------------------------
# Direct APIError raise test
# ---------------------------------------------------------------------------

class TestAPIErrorException:
    """Test the APIError exception class itself."""

    def test_api_error_default_status(self):
        """APIError should map ErrorCode to default HTTP status."""
        err = APIError(code=ErrorCode.NOT_FOUND, message="gone")
        assert err.status_code == 404

    def test_api_error_custom_status(self):
        """APIError should allow overriding HTTP status."""
        err = APIError(code=ErrorCode.INTERNAL_ERROR, message="oops", status_code=503)
        assert err.status_code == 503

    def test_api_error_with_details(self):
        """APIError should accept and store details."""
        err = APIError(
            code=ErrorCode.VALIDATION_ERROR,
            message="bad input",
            details={"field": "name", "reason": "too short"},
        )
        assert err.details == {"field": "name", "reason": "too short"}

    def test_api_error_is_exception(self):
        """APIError should be a proper Exception subclass."""
        assert issubclass(APIError, Exception)
        err = APIError(code=ErrorCode.BAD_REQUEST, message="test")
        assert str(err) == "test"

    def test_api_error_default_details_empty(self):
        """APIError should default to empty details."""
        err = APIError(code=ErrorCode.NOT_FOUND, message="not found")
        assert err.details == {}

    def test_api_error_status_code_mapping(self):
        """All error codes should map to expected HTTP status codes."""
        expected = {
            ErrorCode.VALIDATION_ERROR: 422,
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.AUTH_FAILED: 401,
            ErrorCode.FORBIDDEN: 403,
            ErrorCode.RATE_LIMITED: 429,
            ErrorCode.CONFLICT: 409,
            ErrorCode.BAD_REQUEST: 400,
            ErrorCode.INTERNAL_ERROR: 500,
        }
        for code, status in expected.items():
            err = APIError(code=code, message="test")
            assert err.status_code == status, f"{code} should map to {status}, got {err.status_code}"


# ---------------------------------------------------------------------------
# Schema conformance for success responses
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify that ALL error responses conform to the schema."""

    def test_success_responses_not_wrapped(self, client):
        """Success responses should NOT be wrapped in the error envelope."""
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body  # success should not have error wrapper
        assert body["status"] == "ok"

    def test_error_on_success_has_no_error_key(self, client):
        """Successful agent listing should not have error key."""
        resp = client.get("/agents")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body
