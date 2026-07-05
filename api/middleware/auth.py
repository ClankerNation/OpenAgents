"""
@generated-by: opencode
@platform: OpenCode (opencode.ai)
@timestamp: 2026-07-05T00:00:00+05:30
@session: This file was modified as part of the OpenAgents bounty program. All startup configuration and instructions are documented per project convention.
"

"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_SECRET_AVAILABLE = bool(JWT_SECRET)

# Graceful fallback: missing env returns 500 at runtime, not crash on import
if not JWT_SECRET_AVAILABLE:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Authentication will be unavailable until it is configured."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

_revoked_tokens: set = set()

security = HTTPBearer()


def revoke_jti(jti: str) -> None:
    _revoked_tokens.add(jti)


def is_jti_revoked(jti: str) -> bool:
    return jti in _revoked_tokens


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    JWT_SECRET_AVAILABLE = bool(JWT_SECRET)

# Graceful fallback: missing env returns 500 at runtime, not crash on import
if not JWT_SECRET_AVAILABLE:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "type": "access", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    JWT_SECRET_AVAILABLE = bool(JWT_SECRET)

# Graceful fallback: missing env returns 500 at runtime, not crash on import
if not JWT_SECRET_AVAILABLE:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    JWT_SECRET_AVAILABLE = bool(JWT_SECRET)

# Graceful fallback: missing env returns 500 at runtime, not crash on import
if not JWT_SECRET_AVAILABLE:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = payload.get("jti")
    if jti and is_jti_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return payload


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


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def revoke_token(token: str) -> None:
    payload = decode_token(token)
    jti = payload.get("jti")
    if jti:
        revoke_jti(jti)
