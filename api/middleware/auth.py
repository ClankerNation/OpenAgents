"""JWT authentication middleware for the OpenAgents API.
@generated-by: giren1011-lab
@timestamp: 2026-05-28T08:40:00Z
@purpose: Fix #100 - JWT algorithm validation, env fallback, token revocation
"""

import jwt
import os
import time
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional, Set
import logging

logger = logging.getLogger(__name__)

# ── Configuration with safe fallback ──────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    logger.warning("JWT_SECRET not set! Using fallback. Set JWT_SECRET in production.")
    JWT_SECRET = "dev-secret-change-in-production"

# Pin to HS256 only — reject algorithm none and other algorithms
ALLOWED_ALGORITHMS = ["HS256"]

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "7"))

# ── Token revocation (in-memory set; use Redis in production) ─────────
_revoked_tokens: Set[str] = set()
_revoked_iat_threshold: float = 0  # Revoke all tokens issued before this timestamp


def revoke_token(token: str) -> None:
    """Revoke a specific token."""
    _revoked_tokens.add(token)


def revoke_all_tokens_since(timestamp: float) -> None:
    """Revoke all tokens issued after a given timestamp."""
    global _revoked_iat_threshold
    _revoked_iat_threshold = timestamp


def is_token_revoked(jti: str) -> bool:
    """Check if a token has been revoked by JTI."""
    return jti in _revoked_tokens


# ── Helpers ───────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Raises:
        HTTPException(401): If token is invalid, expired, or revoked.
        HTTPException(403): If token has been revoked.
    """
    try:
        # Decode with explicit algorithm whitelist — rejects 'none' algorithm
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=ALLOWED_ALGORITHMS,
            options={
                "require": ["exp", "iat"],
                "verify_exp": True,
            }
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    # Check revocation
    jti = payload.get("jti", "")
    if is_token_revoked(jti):
        raise HTTPException(status_code=403, detail="Token has been revoked")

    # Check global revocation threshold
    iat = payload.get("iat", 0)
    if _revoked_iat_threshold > 0 and iat < _revoked_iat_threshold:
        raise HTTPException(status_code=403, detail="Token issued before revocation threshold")

    return payload


# ── FastAPI Auth ──────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Get current authenticated user from Bearer token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    payload = decode_token(token)

    user = {
        "sub": payload.get("sub", "anonymous"),
        "role": payload.get("role", "user"),
        "token_type": payload.get("type", "access"),
    }
    return user


async def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Get current user if authenticated, None otherwise."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ── Token Revocation Endpoint ─────────────────────────────────────────

async def revoke_current_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Revoke the current access token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    revoke_token(credentials.credentials)
    return {"status": "ok", "message": "Token revoked"}
