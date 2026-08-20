"""
@contributor rafaio1
@timestamp 2026-08-20T00:00:00Z
@env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from datetime import datetime, timedelta
from typing import Optional

# Safe fallback for JWT_SECRET to prevent startup crash
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security_bearer = HTTPBearer(auto_error=False)
security_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)

# In-memory store for API keys (would be DB in production)
# Maps hashed_key -> user_data
_api_keys_store: dict[str, dict] = {}


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
        # Pin algorithm to HS256 only to prevent "none" algorithm bypass
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key(user_id: str, address: str, roles: list = None) -> dict:
    """Generate a new API key for a user. Returns the raw key once and stores the hash."""
    raw_key = f"oa_{secrets.token_urlsafe(32)}"
    hashed = hash_api_key(raw_key)
    
    _api_keys_store[hashed] = {
        "id": user_id,
        "address": address,
        "roles": roles or [],
        "created_at": datetime.utcnow().isoformat(),
        "active": True,
    }
    
    return {
        "key": raw_key,
        "prefix": raw_key[:8],
        "created_at": _api_keys_store[hashed]["created_at"],
    }


def revoke_api_key(hashed_key: str) -> bool:
    """Revoke an API key by marking it inactive."""
    if hashed_key in _api_keys_store:
        _api_keys_store[hashed_key]["active"] = False
        return True
    return False


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key: Optional[str] = Security(security_api_key),
) -> dict:
    """Authenticate via JWT Bearer token OR X-API-Key header."""
    
    # Try API Key first
    if api_key:
        hashed = hash_api_key(api_key)
        key_data = _api_keys_store.get(hashed)
        
        if not key_data:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not key_data.get("active", False):
            raise HTTPException(status_code=401, detail="API key revoked")
            
        return {
            "id": key_data["id"],
            "address": key_data["address"],
            "roles": key_data.get("roles", []),
            "auth_method": "api_key",
        }
    
    # Fall back to JWT
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)
        
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
