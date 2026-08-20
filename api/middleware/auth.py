# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""JWT and API Key authentication middleware for the OpenAgents API."""

import hashlib
import jwt
import os
import secrets
from fastapi import Request, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from datetime import datetime, timedelta, timezone
from typing import Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# In-memory store for API keys (replace with DB in production)
# key_hash -> {"user_id": str, "address": str, "roles": list, "created_at": datetime}
_api_keys: dict[str, dict] = {}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(user_id: str, address: str, roles: list = None) -> dict:
    """Generate a new API key. Returns the unhashed key once."""
    raw_key = f"oak_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    _api_keys[key_hash] = {
        "user_id": user_id,
        "address": address,
        "roles": roles or [],
        "created_at": datetime.now(timezone.utc),
    }
    return {
        "key": raw_key,
        "key_id": key_hash[:16],
        "created_at": _api_keys[key_hash]["created_at"].isoformat(),
    }


def revoke_api_key(key_id: str) -> bool:
    """Revoke an API key by its ID (first 16 chars of hash)."""
    for full_hash in list(_api_keys.keys()):
        if full_hash.startswith(key_id):
            del _api_keys[full_hash]
            return True
    return False


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """Authenticate via JWT Bearer token OR X-API-Key header."""
    # Try API key first
    if api_key:
        key_hash = _hash_api_key(api_key)
        key_data = _api_keys.get(key_hash)
        if not key_data:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        return {
            "id": key_data["user_id"],
            "address": key_data["address"],
            "roles": key_data["roles"],
            "auth_method": "api_key",
        }

    # Fall back to JWT
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

    raise HTTPException(status_code=401, detail="Authentication required: provide JWT Bearer token or X-API-Key header")


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
