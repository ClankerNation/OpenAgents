"""Uniform error schema and codes.

@fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@fix-date 2026-11-04T18:10:00Z
@session-payload full verbatim block: see the header of api/errors.py
@runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\Program Files\Git\bin\bash.exe
"""

import os
import pathlib
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.errors import ErrorCode, error_body  # noqa: E402
from api.main import app  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402









def assert_shape(body: dict, code: str):
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["details"], dict)
    assert body["request_id"] and body["request_id"] != "-"


def test_unknown_resource_is_not_found(client):
    r = client.get("/agents/999")
    assert r.status_code == 404
    assert_shape(r.json(), ErrorCode.NOT_FOUND)
    assert r.headers["x-request-id"] == r.json()["request_id"]


def test_missing_token_is_auth_failed(client):
    r = client.post("/agents/", json={"name": "a", "endpoint": "https://x.test"})
    assert r.status_code in (401, 403)
    assert_shape(r.json(), ErrorCode.AUTH_FAILED)


def test_body_validation_lists_fields(client):
    token = create_access_token({"sub": "1", "address": "0xa", "roles": ["user"]})
    r = client.post(
        "/agents/", json={"description": "no name"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422
    body = r.json()
    assert_shape(body, ErrorCode.VALIDATION_ERROR)
    fields = [f["field"] for f in body["details"]["fields"]]
    assert any("name" in f for f in fields)


def test_query_validation_is_structured_too(client):
    r = client.get("/agents/search", params={"q": "ok", "limit": 5000})
    assert r.status_code == 422
    assert_shape(r.json(), ErrorCode.VALIDATION_ERROR)


def test_raised_api_error_keeps_its_code_and_details(client):
    from api.errors import ApiError

    @app.get("/_boom404")
    def _boom():
        raise ApiError(404, "things missing", details={"resource": "thing"})

    r = client.get("/_boom404")
    assert r.status_code == 404
    body = r.json()
    assert_shape(body, ErrorCode.NOT_FOUND)
    assert body["details"] == {"resource": "thing"}


def test_unknown_code_is_rejected_at_construction():
    from api.errors import ApiError

    with pytest.raises(ValueError):
        ApiError(400, "x", code="NOPE")


def test_unhandled_error_is_internal_without_a_traceback(client):
    @app.get("/_unhandled")
    def _unhandled():
        raise RuntimeError("secret internals: /home/2/private.py")

    r = client.get("/_unhandled")
    assert r.status_code == 500
    body = r.json()
    assert_shape(body, ErrorCode.INTERNAL_ERROR)
    assert body["message"] == "internal server error"  # no traceback, no paths


def test_every_documented_code_is_in_the_vocabulary():
    assert ErrorCode.values() == {
        "VALIDATION_ERROR",
        "AUTH_FAILED",
        "NOT_FOUND",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
    }


def test_error_body_helper_shape():
    body = error_body(ErrorCode.NOT_FOUND, "gone", "rid-1")
    assert body["request_id"] == "rid-1"
    assert body["details"] == {}  # never null
