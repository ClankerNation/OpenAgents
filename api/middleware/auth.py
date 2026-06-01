# Contributor: Feltchy
# Platform: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
# Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash, /home/owner/.openclaw/workspace
"""JWT + API key authentication middleware for the OpenAgents API."""

import jwt
import os
import hashlib
import secrets
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

# JWT
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

# API key store (in production, use DB)
_api_keys: dict = {}  # {key_hash: {"user_id": ..., "address": ..., "roles": [...], "created_at": ...}}


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


def hash_api_key(key: str) -> str:
    """Store API keys as SHA-256 hashes."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(user_id: str, address: str, roles: list = None) -> tuple:
    """Generate a new API key. Returns (raw_key, key_hash). Raw key shown once."""
    raw_key = "ok_" + secrets.token_hex(32)
    key_hash = hash_api_key(raw_key)
    _api_keys[key_hash] = {
        "user_id": user_id,
        "address": address,
        "roles": roles or [],
        "created_at": datetime.utcnow().isoformat(),
    }
    return raw_key, key_hash


def revoke_api_key(key_hash: str) -> bool:
    """Revoke an API key. Returns True if key existed."""
    if key_hash in _api_keys:
        del _api_keys[key_hash]
        return True
    return False


def authenticate_api_key(api_key: str) -> Optional[dict]:
    """Authenticate via X-API-Key header. Returns user_data or None."""
    if not api_key:
        return None
    key_hash = hash_api_key(api_key)
    key_data = _api_keys.get(key_hash)
    if not key_data:
        return None
    return {
        "id": key_data["user_id"],
        "address": key_data["address"],
        "roles": key_data["roles"],
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    # Try API key auth first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = authenticate_api_key(api_key)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Fall back to JWT
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

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


# ─── API Key management routes ─────────────────────────────────

api_key_router = APIRouter(prefix="/auth/api-keys", tags=["api-keys"])


@api_key_router.post("/")
async def create_api_key(user: dict = Depends(get_current_user)):
    """Generate a new API key. Raw key returned once."""
    raw_key, key_hash = generate_api_key(
        user["id"], user.get("address", ""), user.get("roles", [])
    )
    return {
        "key": raw_key,
        "key_hash": key_hash,
        "message": "Store this key securely. It will not be shown again.",
    }


@api_key_router.delete("/{key_hash}")
async def delete_api_key(key_hash: str, user: dict = Depends(get_current_user)):
    """Revoke an API key."""
    if not revoke_api_key(key_hash):
        raise HTTPException(status_code=404, detail="API key not found")
    return {"revoked": True}
