"""Shared structured API error response helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request

VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
AUTH_FAILED = "AUTH_FAILED"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL_ERROR = "INTERNAL_ERROR"


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def map_status_to_code(status_code: int) -> str:
    if status_code in (400, 422):
        return VALIDATION_ERROR
    if status_code == 404:
        return NOT_FOUND
    if status_code in (401, 403):
        return AUTH_FAILED
    if status_code == 429:
        return RATE_LIMITED
    return INTERNAL_ERROR


def make_error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": get_request_id(request),
    }

