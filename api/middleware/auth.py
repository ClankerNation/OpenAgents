"""
@contributor-info
  agent: opencode (deepseek-v4-pro)
  timestamp: 2026-06-08T01:10:00Z
  platform_instructions: You are opencode, an interactive CLI tool that helps users with software engineering tasks. The user asks to continue generating income and running background monitors.
  fix: #177 - Add API key authentication alongside JWT, with key generation and revocation endpoints
"""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)
_api_keys: dict = {}

api_key_router = APIRouter(prefix="/auth/api-keys", tags=["auth"])


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@api_key_router.post("/")
async def create_api_key(user=Depends(lambda: None)):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    prefix = "oak_"
    raw_key = prefix + secrets.token_hex(24)
    hashed = _hash_key(raw_key)
    user_id = user.get("id", user.get("sub"))
    if user_id not in _api_keys:
        _api_keys[user_id] = []
    _api_keys[user_id].append({
        "id": len(_api_keys[user_id]) + 1,
        "hash": hashed,
        "prefix": raw_key[:10],
        "created_at": datetime.utcnow().isoformat(),
    })
    return {"api_key": raw_key, "prefix": raw_key[:10], "id": len(_api_keys[user_id])}


@api_key_router.delete("/{key_id}")
async def revoke_api_key(key_id: int, user=Depends(lambda: None)):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = user.get("id", user.get("sub"))
    if user_id in _api_keys and 0 <= key_id - 1 < len(_api_keys[user_id]):
        _api_keys[user_id].pop(key_id - 1)
        return {"revoked": True}
    raise HTTPException(status_code=404, detail="API key not found")


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


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None,
) -> dict:
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return {
            "id": payload.get("sub"),
            "address": payload.get("address"),
            "roles": payload.get("roles", []),
            "auth_method": "jwt",
        }

    api_key = None
    if request:
        api_key = request.headers.get("X-API-Key")
    if api_key:
        hashed = _hash_key(api_key)
        for uid, keys in _api_keys.items():
            for k in keys:
                if k["hash"] == hashed:
                    return {
                        "id": uid,
                        "address": None,
                        "roles": ["api_key"],
                        "auth_method": "api_key",
                    }
        raise HTTPException(status_code=401, detail="Invalid API key")

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
