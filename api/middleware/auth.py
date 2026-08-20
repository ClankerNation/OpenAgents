# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
import time
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional, Set

# Graceful env fallback — fail with clear error instead of KeyError crash
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        "Set it before starting the application."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# In-memory token revocation set (production should use Redis/DB)
_revoked_tokens: Set[str] = set()


def revoke_token(token: str) -> None:
    """Add a token to the revocation set."""
    _revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    return token in _revoked_tokens


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
        # Pin algorithm to HS256 only — reject 'none' and all other algorithms
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials

    # Check revocation before decoding
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


def refresh_access_token(refresh_token: str) -> dict:
    """Validate refresh token and issue new access token."""
    if is_token_revoked(refresh_token):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    address = payload.get("address")
    roles = payload.get("roles", [])

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    # Rotate: revoke old refresh token and issue new pair
    revoke_token(refresh_token)
    return generate_login_tokens(user_id, address, roles)
