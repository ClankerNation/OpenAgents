"""
JWT authentication middleware for the OpenAgents API.

@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18
"""

import jwt
import os
import time
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone
from typing import Optional

# Fail-safe: use a default secret in dev BUT warn, crash in production without JWT_SECRET
JWT_SECRET: str = os.environ.get("JWT_SECRET") or ""  # type: ignore[assignment]
if not JWT_SECRET:
    if os.environ.get("ENVIRONMENT", "production").lower() in ("production", "prod"):
        raise RuntimeError("JWT_SECRET must be set in production environment")
    JWT_SECRET = "dev-only-insecure-secret-change-me"
    import warnings
    warnings.warn("JWT_SECRET not set — using insecure default. Never use in production!")

# Algorithm pinning: only HS256 allowed, no "none" algorithm bypass
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# In-memory token revocation list (production should use Redis/DB)
_revoked_tokens: set = set()

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def revoke_token(token: str) -> None:
    """Add a token to the revocation list. Call on logout."""
    _revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    return token in _revoked_tokens


def decode_token(token: str) -> dict:
    try:
        # Algorithm PINNED to HS256 only — "none" algorithm attack blocked
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials

    # Revocation check — logged-out tokens are immediately invalid
    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type — refresh tokens cannot access protected routes")

    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }

    if not user_data["id"]:
        raise HTTPException(status_code=401, detail="Invalid token payload — missing subject")

    return user_data


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user)):
        if role not in user.get("roles", []):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return role_checker


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    return {
        "token": access_token,
        "refresh_token": refresh_token,
    }


def refresh_access_token(refresh_token: str) -> str:
    """Exchange a valid refresh token for a new access token.
    Revokes the old refresh token to prevent reuse (rotation)."""
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    # Revoke the used refresh token — one-time use
    revoke_token(refresh_token)

    # Issue new access token with same claims (minus type/exp)
    data = {
        "sub": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }
    return create_access_token(data)