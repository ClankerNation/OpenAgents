"""
Contributor Metadata (required for bounty #177)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
"""

"""JWT and API key authentication middleware for the OpenAgents API."""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from datetime import datetime, timedelta
from typing import Optional, Dict

# BUG: No fallback � if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ.get("JWT_SECRET", "default-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# In-memory API key store (hashed). In production, use a database.
_api_keys: Dict[str, dict] = {}


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


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
        # BUG: Algorithm not pinned in decode � attacker can forge a token with
        # alg: "none" and bypass signature verification entirely
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header),
) -> dict:
    # Try API key first
    if api_key:
        key_hash = _hash_api_key(api_key)
        if key_hash in _api_keys:
            key_data = _api_keys[key_hash]
            if key_data.get("revoked"):
                raise HTTPException(status_code=401, detail="API key has been revoked")
            return {
                "id": key_data.get("user_id"),
                "address": key_data.get("address"),
                "roles": key_data.get("roles", []),
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

    raise HTTPException(status_code=401, detail="Authentication required")


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


def generate_api_key(user_id: str, address: str, roles: list = None, premium: bool = False) -> dict:
    """Generate a new API key and store its hash."""
    raw_key = secrets.token_urlsafe(32)
    key_hash = _hash_api_key(raw_key)
    key_id = secrets.token_hex(8)

    _api_keys[key_hash] = {
        "id": key_id,
        "user_id": user_id,
        "address": address,
        "roles": roles or [],
        "premium": premium,
        "revoked": False,
        "created_at": datetime.utcnow().isoformat(),
    }

    return {
        "id": key_id,
        "api_key": raw_key,
        "premium": premium,
        "created_at": _api_keys[key_hash]["created_at"],
    }


def revoke_api_key(key_id: str) -> bool:
    """Revoke an API key by its ID."""
    for key_hash, data in _api_keys.items():
        if data.get("id") == key_id:
            data["revoked"] = True
            return True
    return False


def list_api_keys(user_id: str) -> list:
    """List all API keys for a user."""
    return [
        {
            "id": data["id"],
            "premium": data.get("premium", False),
            "revoked": data.get("revoked", False),
            "created_at": data.get("created_at"),
        }
        for data in _api_keys.values()
        if data.get("user_id") == user_id
    ]
