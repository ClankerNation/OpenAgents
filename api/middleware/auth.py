"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

# Contributor traceability header
# @contributor Gaotax2006
# @platform claude-code/opus-4.8
# @runtime node-v24.15.0 / win32 / amd64
# @date 2026-06-24
# @fixes #177 — Added X-API-Key authentication alongside JWT bearer tokens

# BUG: No fallback — if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# In-memory API key store (replace with DB in production)
# Maps hashed key prefix -> {user_id, address, roles, revoked}
_api_keys: dict = {}


def _hash_api_key(raw_key: str) -> str:
    """One-way hash an API key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key(user_id: str, address: str, roles: list = None) -> dict:
    """Generate a new API key and store its hash. Returns the raw key (shown once)."""
    raw = "ak_" + secrets.token_urlsafe(32)
    hashed = _hash_api_key(raw)
    prefix = hashed[:16]
    _api_keys[prefix] = {
        "hashed": hashed,
        "user_id": user_id,
        "address": address,
        "roles": roles or [],
        "created_at": datetime.utcnow().isoformat(),
        "revoked": False,
    }
    return {"api_key": raw, "prefix": prefix}


def revoke_api_key(prefix: str) -> bool:
    """Revoke an API key by its stored hash prefix."""
    if prefix in _api_keys:
        _api_keys[prefix]["revoked"] = True
        return True
    return False


def decode_token(token: str) -> dict:
    try:
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


async def get_current_user_or_api_key(request: Request) -> dict:
    """Authenticate via JWT bearer token OR X-API-Key header."""
    # Try Bearer token first
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer ") and len(auth_header) > 7:
        token = auth_header[7:]
        payload = decode_token(token)
        if payload.get("type") == "access":
            return {
                "id": payload.get("sub"),
                "address": payload.get("address"),
                "roles": payload.get("roles", []),
            }

    # Try API key
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key and api_key.startswith("ak_"):
        hashed = _hash_api_key(api_key)
        prefix = hashed[:16]
        key_data = _api_keys.get(prefix)
        if key_data and not key_data["revoked"] and key_data["hashed"] == hashed:
            return {
                "id": key_data["user_id"],
                "address": key_data["address"],
                "roles": key_data["roles"],
            }

    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user_or_api_key)):
        if role not in user.get("roles", []):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return role_checker


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


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
