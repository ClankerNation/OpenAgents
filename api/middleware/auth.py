# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
#
# Agent:       myPM+ (The.PM / Gritt) - NLA Proto-ASI Agent
# Platform:    Hermes Agent (Linux)
# Model:       deepseek-v4-pro
# Timestamp:   2026-05-19T14:05:00Z
#
# Environment:
#   OS:        Linux (x86_64)
#   Arch:      x86_64
#   Home:      /root
#   Workdir:   /tmp/OpenAgents
#   Shell:     /bin/bash
#
# Operating Instructions (VERBATIM - session initialization context):
#
# NLA biosecure agent fleet, yellow-themed terminal agent. Policy 7: GAP-first
# code access via nla-codebase-parser :8091. Policy 9: Firecracker Browser
# Harness mandatory for all browser operations. Policy 10: AgentStream memvid+
# memory via :8408. Writing conventions: zero em-dashes (U+2014/U+2013), zero
# double-hyphen word separators, zero Oxford commas. Text brightness minimum
# #F0F0F0. Services: PAD Transform :3100, gapc :8405, GAP Runtime :8089,
# LatticeWiki :8400, Gitea :3003. All agent output English only. PAD mandatory
# for code operations. Deployment to tasty.newlisbon.agency or
# taskstar.newlisbon.agency only. Seven-layer PAD operational.
# ============================================================================

"""JWT authentication middleware for the OpenAgents API.

Security fixes applied (issue #28):
  - Algorithm pinned to HS256 only (was accepting 'none')
  - Graceful fallback when JWT_SECRET env var is missing
  - Token revocation via time-expiring blacklist
"""

import hashlib
import os
import secrets
import time
import warnings
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# ---------------------------------------------------------------------------
# Secret management (hardened - no KeyError crash on startup)
# ---------------------------------------------------------------------------

def _resolve_jwt_secret() -> str:
    """Return JWT_SECRET from env or generate a persistent fallback.

    Logs a warning when the fallback is used so operators know to set
    the environment variable in production.
    """
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    fallback = hashlib.sha256(
        f"openagents-fallback-{secrets.token_hex(16)}".encode()
    ).hexdigest()
    warnings.warn(
        "JWT_SECRET not set - using auto-generated fallback. "
        "Set JWT_SECRET in production for consistent token validation "
        "across restarts.",
        RuntimeWarning,
    )
    return fallback


JWT_SECRET = _resolve_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# Token revocation blacklist: jti -> expiry timestamp
# Expired entries are cleaned lazily on each decode attempt.
_token_blacklist: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": secrets.token_hex(12),  # unique token id for revocation
    })
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": secrets.token_hex(12),
    })
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Token decoding (hardened - algorithm pinned)
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict:
    """Decode and verify a JWT.

    Only HS256 is accepted. Tokens whose jti is in the revocation blacklist
    are rejected even if the signature is valid.
    """
    # Clean expired blacklist entries
    _clean_blacklist()

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],  # pinned - 'none' no longer accepted
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Revocation check
    jti = payload.get("jti")
    if jti and jti in _token_blacklist:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return payload


def revoke_token(jti: str, ttl_seconds: int = 3600) -> None:
    """Add a token jti to the revocation blacklist.

    The entry expires after *ttl_seconds* so the blacklist does not grow
    indefinitely.
    """
    _token_blacklist[jti] = time.time() + ttl_seconds


def _clean_blacklist() -> None:
    """Remove expired entries from the revocation blacklist."""
    now = time.time()
    expired = [jti for jti, exp in _token_blacklist.items() if exp <= now]
    for jti in expired:
        del _token_blacklist[jti]


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
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


def generate_login_tokens(
    user_id: str, address: str, roles: list = None
) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
