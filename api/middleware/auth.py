"""
@generated-by
  Agent: OpenCode Agent (opencode/deepseek-v4-flash-free)
  Timestamp: 2026-07-16T19:12:00Z
  Startup Configuration:
    Instructions files loaded:
    - AGENTS.md (autonomy policy, loop entrypoint, definition of done)
    - LOOP.md (conceptual contribution cycle diagram)
    - LOOP_EXECUTION.md (phase-by-phase procedure)
    - SKILLS.md (reusable named procedures)
    - RULES.md (non-negotiable policy rules)
    - PR_SHEPHERD.md (PR shepherd agent mandate and procedure)
    - memory.md (internal vs external memory distinction)
    - orgs/tensorflow.md (TensorFlow contribution runbook)
    - orgs/ray.md (Ray contribution runbook)
    - orgs/kubeflow.md (Kubeflow contribution runbook)
    - orgs/evalai.md (EvalAI contribution runbook)
    - opencode.json (OpenCode tool permission configuration)
    Agent instructions: Bounty issue #100 — Fix JWT auth middleware accepts
    algorithm none. Follow LOOP_EXECUTION.md phases. Repository:
    ClankerNation/OpenAgents. Issue: #100 "[Bounty $8k][API] Fix JWT auth
    middleware accepts algorithm none — v2 implementation". First-PR-wins
    racing format. 2-hour window from claim. Must include @generated-by doc
    block with name, timestamp, full startup config, and runtime info. Must
    include tests for all functionality. Must satisfy all acceptance criteria.
  Runtime Info:
    OS: win32
    Architecture: 64-bit
    Home Directory: C:\\Users\\shiva
    Working Directory: C:\\Users\\shiva\\OneDrive\\Documents\\demo\\contribute\\OpenAgents
    Python: 3.11
    pyjwt: 2.13.0
"""

"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

# Graceful env fallback: error at runtime, not crash at import time
JWT_SECRET: Optional[str] = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# In-memory token revocation set (production would use Redis/DB)
_revoked_tokens: set = set()

security = HTTPBearer(auto_error=False)


def _ensure_secret() -> str:
    """Return JWT_SECRET or raise a clear HTTPException.

    Called at runtime (not import time) so a missing secret produces
    a 500 error instead of crashing the entire application on startup.
    """
    if JWT_SECRET is None:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: JWT_SECRET not set",
        )
    return JWT_SECRET


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    secret = _ensure_secret()
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    secret = _ensure_secret()
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # FIXED: Algorithm pinned to ["HS256"] only — "none" is not allowed,
        # preventing attackers from forging tokens with alg: "none" and no signature.
        secret = _ensure_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def revoke_token(token: str) -> None:
    """Add a token to the revocation set."""
    _revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    return token in _revoked_tokens


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials

    # FIXED: Check token revocation — logged-out or compromised tokens
    # are rejected even before their natural expiration.
    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

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
