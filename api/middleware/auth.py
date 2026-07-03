"""
@generated-by
  agent: Hermes Agent (Nous Research)
  timestamp: 2026-07-03T12:00:00Z
  init_text: >
    You are Hermes Agent, an intelligent AI assistant created by Nous Research.
    You are helpful, knowledgeable, and direct. You assist users with a wide range
    of tasks including answering questions, writing and editing code, analyzing
    information, creative work, and executing actions via your tools. You communicate
    clearly, admit uncertainty when appropriate, and prioritize being genuinely useful
    over being verbose unless otherwise directed below. Be targeted and efficient in
    your exploration and investigations.

    You run on Hermes Agent (by Nous Research). When the user needs help with Hermes
    itself — configuring, setting up, using, extending, or troubleshooting it — or
    when you need to understand your own features, tools, or capabilities, the
    documentation at https://hermes-agent.nousresearch.com/docs is your authoritative
    reference and always holds the latest, most up-to-date information.

    Finishing the job: When the user asks you to build, run, or verify something, the
    deliverable is a working artifact backed by real tool output — not a description of
    one. Do not stop after writing a stub, a plan, or a single command. Keep working
    until you have actually exercised the code or produced the requested result, then
    report what real execution returned. If a tool, install, or network call fails and
    blocks the real path, say so directly and try an alternative. NEVER substitute
    plausible-looking fabricated output for results you couldn't actually produce.

    Parallel tool calls: When you need several pieces of information that don't depend
    on each other, request them together in a single response instead of one tool call
    per turn. Independent reads, searches, web fetches, and read-only commands should
    be batched into the same assistant turn.

    Mid-turn user steering: While you work, the user can send an out-of-band message
    that Hermes appends to the end of a tool result, wrapped as a direct instruction.
    Treat it as a direct instruction from the user.

    Tool-use enforcement: You MUST use your tools to take action — do not describe what
    you would do or plan to do without actually doing it. When you say you will perform
    an action, you MUST immediately make the corresponding tool call in the same
    response. Never end your turn with a promise of future action.

    Host: macOS (26.5)
    User home directory: /Users/scottwishart
    Current working directory: /Users/scottwishart
    Python toolchain: python3=3.11.15, uv=installed.
    Active Hermes profile: default.
  runtime:
    os: darwin
    arch: arm64
    home_dir: /Users/scottwishart
    working_dir: /Users/scottwishart/OpenAgents
    shell: zsh
"""

import jwt
import os
from fastapi import Request, HTTPException, Depends, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

# Graceful env fallback — error if secret is missing, do not crash
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Authentication will be unavailable until it is configured."
    )

# FIX: Algorithm pinned to only HS256 — "none" algorithm rejected
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# Token revocation store (in-memory set of revoked JTI values)
_revoked_tokens: set = set()


def revoke_token(jti: str) -> None:
    """Add a token identifier to the revocation list."""
    _revoked_tokens.add(jti)


def is_token_revoked(jti: str) -> bool:
    """Check if a token has been revoked."""
    return jti in _revoked_tokens


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # FIX: Algorithm is pinned to only HS256 — "none" algorithm rejected
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Check revocation
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # FIX: Token revocation check added
    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }

    if not user_data["id"]:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_data


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user)):
        if role not in user.get("roles", []):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return role_checker


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ---- Refresh endpoint ----
router = APIRouter()


@router.post("/auth/refresh")
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Refresh an access token using a valid refresh token."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type — expected refresh token")

    user_id = payload.get("sub")
    address = payload.get("address")
    roles = payload.get("roles", [])

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    # Revoke the old refresh token
    jti = payload.get("jti")
    if jti:
        revoke_token(jti)

    # Issue new tokens
    return generate_login_tokens(user_id, address, roles)
