"""JWT authentication middleware for the OpenAgents API.

Contributor traceability:
@contributor claude-code-b3ar-sudo
@platform-config Issue #28 JWT hardening; private credentials, hidden prompts, and local paths intentionally omitted.
@env linux x86_64, Claude Code
@timestamp 2026-05-20T00:00:00Z
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
_REVOKED_TOKEN_IDS: set[str] = set()
_REVOKED_TOKEN_HASHES: set[str] = set()


def get_jwt_secret() -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    return JWT_SECRET


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access", "jti": str(uuid4())})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh", "jti": str(uuid4())})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def reject_unexpected_algorithm(token: str) -> None:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if header.get("alg") != JWT_ALGORITHM:
        raise HTTPException(status_code=401, detail="Invalid token algorithm")


def is_token_revoked(token: str, payload: dict) -> bool:
    token_id = payload.get("jti")
    return token_hash(token) in _REVOKED_TOKEN_HASHES or bool(token_id and token_id in _REVOKED_TOKEN_IDS)


def revoke_token(token: str) -> None:
    payload = decode_token(token, verify_revocation=False)
    token_id = payload.get("jti")
    if token_id:
        _REVOKED_TOKEN_IDS.add(token_id)
    _REVOKED_TOKEN_HASHES.add(token_hash(token))


def decode_token(token: str, verify_revocation: bool = True) -> dict:
    reject_unexpected_algorithm(token)
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if verify_revocation and is_token_revoked(token, payload):
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


def refresh_access_token(refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    data = {
        "sub": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }
    if not data["sub"]:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {
        "token": create_access_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
