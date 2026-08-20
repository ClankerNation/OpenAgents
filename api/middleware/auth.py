# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow
"""JWT and API Key authentication middleware for the OpenAgents API."""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# In-memory store for API keys (replace with DB in production)
# Format: {hashed_key: {"user_id": str, "created_at": datetime}}
_api_keys_store: dict = {}


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(user_id: str) -> dict:
    raw_key = f"oak_{secrets.token_hex(32)}"
    hashed = hash_api_key(raw_key)
    _api_keys_store[hashed] = {"user_id": user_id, "created_at": datetime.utcnow()}
    return {"api_key": raw_key, "prefix": raw_key[:8]}


def revoke_api_key(api_key: str) -> bool:
    hashed = hash_api_key(api_key)
    if hashed in _api_keys_store:
        del _api_keys_store[hashed]
        return True
    return False


def validate_api_key(api_key: str) -> Optional[dict]:
    if not api_key:
        return None
    hashed = hash_api_key(api_key)
    entry = _api_keys_store.get(hashed)
    if entry:
        return {"id": entry["user_id"], "auth_type": "api_key"}
    return None


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
        # BUG: Algorithm not pinned in decode — attacker can forge a token with
        # alg: "none" and bypass signature verification entirely
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256", "none"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    # Try API key first
    if api_key:
        user_data = validate_api_key(api_key)
        if user_data:
            return user_data
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Fall back to JWT bearer token
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_data = {
            "id": payload.get("sub"),
            "address": payload.get("address"),
            "roles": payload.get("roles", []),
            "auth_type": "jwt",
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
