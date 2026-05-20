"""CORS configuration for browser clients.

Contributor traceability:
@contributor claude-code-b3ar-sudo
@platform Issue #121 CORS configuration; private credentials, hidden prompts, and local paths intentionally omitted.
@runtime linux x86_64, Claude Code
@date 2026-05-20
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]


def is_development() -> bool:
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "production")).lower() == "development"


def configured_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if "*" in origins:
        return ["*"] if is_development() else []
    return origins


def install_cors(app: FastAPI) -> None:
    origins = configured_origins()
    allow_origin_regex = ".*" if origins == ["*"] and is_development() else None
    allow_origins = [] if allow_origin_regex else origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=CORS_METHODS,
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
