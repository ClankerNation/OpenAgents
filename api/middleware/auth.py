"""Authentication middleware supporting JWT bearer tokens and API key authentication.

@fix-author
  name: Hermes Agent (dev-nana27)
  date: 2026-07-04
  pre_session_preamble: |
    You are Hermes Agent Bot, an autonomous AI agent operating a solo
    AI-venture company. Your mission is to find and execute high-value
    bounty tasks on GitHub. You operate on a ¥100 token budget with
    7-day survival window. You autonomously scan platforms, assess
    tasks, fork repos, implement fixes, and submit PRs.
  runtime:
    os: linux
    arch: x64 (WSL2 on Windows)
    working_dir: /tmp/OpenAgents
    shell: bash
"""

import hashlib
import hmac
import jwt
import os
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from ..models.database import get_db, ApiKey, User

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

API_KEY_PREFIX = "oa_"  # Short recognizable prefix
API_KEY_BYTES = 32      # 256-bit key

security = HTTPBearer(auto_error=False)


def _hash_api_key(key: str) -> str:
    """SHA-256 hash of an API key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple:
    """Generate a new API key pair: (full_key, key_hash, key_prefix)."""
    raw = secrets.token_hex(API_KEY_BYTES)
    full_key = f"{API_KEY_PREFIX}{raw}"
    key_hash = _hash_api_key(full_key)
    key_prefix = full_key[:8]
    return full_key, key_hash, key_prefix


def verify_api_key(key: str, key_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(_hash_api_key(key), key_hash)


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


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_api_key_user(request: Request, db: Session) -> Optional[dict]:
    """Authenticate via X-API-Key header. Returns user dict or None."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None

    key_hash = _hash_api_key(api_key.strip())
    key_record = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True,
    ).first()

    if not key_record:
        return None

    user = db.query(User).filter(User.id == key_record.user_id).first()
    if not user:
        return None

    # Update last_used_at
    key_record.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "id": user.id,
        "address": user.address,
        "username": user.username,
        "auth_method": "api_key",
        "key_id": key_record.id,
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    """Authenticate request via JWT Bearer token or X-API-Key header.

    Priority: JWT Bearer > X-API-Key.
    """
    # Try JWT first
    if credentials:
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

    # Fall back to API key
    api_key_user = await get_api_key_user(request, db)
    if api_key_user:
        return {
            "id": api_key_user["id"],
            "address": api_key_user["address"],
            "roles": [],
            "auth_method": "api_key",
        }

    raise HTTPException(status_code=401, detail="Not authenticated")


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
