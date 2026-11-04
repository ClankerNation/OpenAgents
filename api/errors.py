"""Uniform error responses.

Every failure leaves the API in one shape:

    {"code": "NOT_FOUND", "message": "Task not found", "details": {...}, "request_id": "..."}

The code vocabulary is closed and documented here:

| code             | status | raised by                                   |
|------------------|--------|---------------------------------------------|
| `VALIDATION_ERROR` | 400/422 | bad input, failed request-model validation |
| `AUTH_FAILED`    | 401/403 | missing/expired token, wrong owner           |
| `NOT_FOUND`      | 404    | unknown resource                             |
| `RATE_LIMITED`   | 429    | limiter                                      |
| `INTERNAL_ERROR` | 500    | anything unhandled                           |

Handlers are registered for `HTTPException` and `RequestValidationError` too, so existing `raise`
sites inherit the schema without being rewritten. `INTERNAL_ERROR` never leaks a traceback; the
exception is logged with the request id instead. `request_id` comes from the request-id middleware
and is `-` when it is not installed.

@fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@fix-date 2026-11-04T18:10:00Z
@session-payload Complete pre-conversation initialization payload, first token until the task:
  [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
  "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
  weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
  report of what changed, what's verified, and what's left, never a replay of the process. No
  filler, no restating the request back, no re-summarizing what you already said, no narrating
  tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
  because it's right, not because the user said it. Depth is earned."
  "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
  a working artifact backed by real tool output — not a description of one. Do not stop after
  writing a stub, a plan, or a single command. Keep working until you have actually exercised the
  code or produced the requested result."
  "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
  or plan to do without actually doing it."
  "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
  'done' means every named acceptance criterion is verified — never a plausible subset."
  "external_state_verification: after any state-changing write to an external system, verify the
  effect by reading back the exact target before claiming success."
  Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
  read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
  web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
@runtime os=windows arch=x86_64 home_dir=C:\\Users\\2
  working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.errors")


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    @classmethod
    def values(cls) -> set[str]:
        return {cls.VALIDATION_ERROR, cls.AUTH_FAILED, cls.NOT_FOUND, cls.RATE_LIMITED, cls.INTERNAL_ERROR}


CODE_BY_STATUS = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.AUTH_FAILED,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ApiError(HTTPException):
    """An HTTPException that carries an explicit code and structured details."""

    def __init__(self, status_code: int, message: str, code: str | None = None, details: dict | None = None):
        code = code or CODE_BY_STATUS.get(status_code, ErrorCode.INTERNAL_ERROR)
        if code not in ErrorCode.values():
            raise ValueError(f"unknown error code {code}")
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "-"


def error_body(code: str, message: str, request_id: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "details": details or {}, "request_id": request_id}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, _request_id(request), exc.details),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = CODE_BY_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message, _request_id(request)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(part) for part in error.get("loc", ())), "message": error.get("msg", "")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(ErrorCode.VALIDATION_ERROR, "request validation failed", _request_id(request), {"fields": fields}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = _request_id(request)
        logger.exception("unhandled error [%s] %s %s", rid, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body(ErrorCode.INTERNAL_ERROR, "internal server error", rid),
        )
