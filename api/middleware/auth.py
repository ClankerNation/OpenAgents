"""
@fix-author
  name: barnacleagent-svg
  date: 2026-05-31
  platform_init: |
    You are GLM (General Language model), a large language model developed by Z.ai.
    Designed to understand and generate human-like text through training on diverse text data.
    Capabilities include answering questions, providing information, and engaging in conversations.
    Operating as an interactive CLI tool for software engineering tasks.
    Goal: Earn $200 from OSS bounties using barnacleagent-svg GitHub account ONLY.
    Instructions: Fix auth.py to support API key authentication alongside JWT.
    Requirements: X-API-Key header support, hashed storage, key generation/revocation endpoints,
    rate limit differentiation, contributor metadata, CONTRIBUTORS.json update.
  runtime:
    os: linux
    arch: x86_64
    working_dir: /home/bennett/projects/OSS-Contributions/OpenAgents/api/middleware
    shell: bash

Authentication middleware supporting both JWT Bearer tokens and API key authentication.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

hashed_api_keys: dict[str, dict] = {}
api_key_metadata: dict[str, dict] = {}


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    id: str
    created_at: str


class ApiKeyRevokeResponse(BaseModel):
    status: str
    message: str


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _generate_api_key() -> tuple[str, str, str]:
    raw_key = f"oa_{secrets.token_hex(32)}"
    key_id = f"key_{secrets.token_hex(8)}"
    hashed = _hash_api_key(raw_key)
    return raw_key, key_id, hashed


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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    api_key = request.headers.get("X-API-Key", "")

    if api_key:
        hashed = _hash_api_key(api_key)
        if hashed in hashed_api_keys:
            key_data = hashed_api_keys[hashed]
            return {
                "id": key_data.get("user_id", "api-user"),
                "auth_method": "api_key",
                "key_id": key_data.get("key_id"),
                "roles": ["api", "premium"],
            }
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide Authorization: Bearer <token> or X-API-Key: <key>",
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
        "auth_method": "jwt",
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
