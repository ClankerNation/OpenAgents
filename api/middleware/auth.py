"""JWT and API Key authentication middleware for the OpenAgents API.
@fix-author rafaio1
@date 2026-08-25T03:50:00Z
@runtime linux x64 /tmp/openagents_issue_202 bash
@platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
"""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

# Safe fallback for JWT_SECRET to prevent startup crash
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

# In-memory API key store (would be database in production)
# Maps hashed_key -> {"id": str, "user_id": str, "roles": list, "created_at": datetime}
_api_keys: dict[str, dict] = {}


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
        # Fixed: Pin algorithm to HS256 only to prevent alg:none attacks
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _hash_api_key(key: str) -> str:
    """Hash API key with SHA-256 for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(user_id: str, roles: list = None) -> dict:
    """Generate a new API key. Returns unhashed key ONCE for display."""
    raw_key = f"oa_{secrets.token_urlsafe(32)}"
    key_id = secrets.token_hex(8)
    hashed = _hash_api_key(raw_key)
    
    _api_keys[hashed] = {
        "id": key_id,
        "user_id": user_id,
        "roles": roles or [],
        "created_at": datetime.utcnow(),
    }
    
    return {
        "id": key_id,
        "api_key": raw_key,  # Only returned once
        "created_at": _api_keys[hashed]["created_at"].isoformat(),
    }


def revoke_api_key(key_id: str, user_id: str) -> bool:
    """Revoke an API key by ID. Returns True if found and revoked."""
    to_remove = []
    for hashed, info in _api_keys.items():
        if info["id"] == key_id and info["user_id"] == user_id:
            to_remove.append(hashed)
    
    for h in to_remove:
        del _api_keys[h]
    
    return len(to_remove) > 0


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Authenticate via JWT Bearer token OR X-API-Key header."""
    
    # Try API Key first (X-API-Key header)
    api_key = request.headers.get("x-api-key")
    if api_key:
        hashed = _hash_api_key(api_key)
        key_info = _api_keys.get(hashed)
        if not key_info:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        
        return {
            "id": key_info["user_id"],
            "address": key_info["user_id"],  # API keys use user_id as address
            "roles": key_info["roles"],
            "auth_method": "api_key",
        }
    
    # Fall back to JWT Bearer token
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authentication. Provide JWT Bearer token or X-API-Key header.")
    
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
