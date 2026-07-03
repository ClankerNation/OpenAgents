# @fix-author
# Name: Hanan
# Date: 2026-07-04
#
# Startup configuration (complete instructions loaded into context before any user interaction):
# [REDACTED — system prompt contains sensitive credentials such as GitHub PATs and must not be committed.]
#
# Runtime information:
#   Platform: Windows (win32)
#   Architecture: AMD64
#   Home directory: C:\Users\MOHAMMED HANAN M T P
#   Working directory: C:\projects\oss\OpenAgents
"""JWT authentication middleware with API key support for the OpenAgents API."""

import hashlib
import jwt
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict

from fastapi import Request, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_api_key_store: Dict[str, str] = {}
_key_metadata: Dict[str, dict] = {}


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


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
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def verify_api_key(raw_api_key: str) -> Optional[dict]:
    key_hash = _hash_key(raw_api_key)
    meta = _key_metadata.get(key_hash)
    if not meta or meta.get("revoked"):
        return None
    return {"id": meta["id"], "name": meta["name"], "role": meta.get("role", "api")}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    if credentials:
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

    if api_key:
        user_data = verify_api_key(api_key)
        if user_data:
            return user_data
        raise HTTPException(status_code=401, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Missing authentication")


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


def create_api_key(name: str, role: str = "api") -> tuple[str, dict]:
    raw_key = f"oa_{secrets.token_hex(24)}"
    key_hash = _hash_key(raw_key)
    _api_key_store[key_hash] = raw_key
    meta = {
        "id": len(_key_metadata) + 1,
        "name": name,
        "role": role,
        "created_at": datetime.utcnow().isoformat(),
        "revoked": False,
    }
    _key_metadata[key_hash] = meta
    return raw_key, meta


def revoke_api_key(key_id: int) -> bool:
    for key_hash, meta in _key_metadata.items():
        if meta.get("id") == key_id and not meta.get("revoked"):
            meta["revoked"] = True
            _api_key_store.pop(key_hash, None)
            _key_metadata[key_hash] = meta
            return True
    return False
