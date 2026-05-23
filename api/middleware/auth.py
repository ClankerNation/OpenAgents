"""JWT authentication middleware for the OpenAgents API."""

import hashlib
import jwt
import os
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

api_keys: dict[str, dict] = {}


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
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        hashed = hashlib.sha256(api_key.encode()).hexdigest()
        if hashed in api_keys:
            return api_keys[hashed]
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not credentials:
        raise HTTPException(status_code=401, detail="No auth credentials provided")

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


def generate_api_key(user_id: str, address: str) -> dict:
    raw_key = f"oa_{secrets.token_hex(24)}"
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    api_keys[hashed] = {
        "id": user_id,
        "address": address,
        "roles": ["api"],
        "api_key_hash": hashed,
    }
    return {"api_key": raw_key, "id": user_id}


def revoke_api_key(api_key_hash: str) -> bool:
    if api_key_hash in api_keys:
        del api_keys[api_key_hash]
        return True
    return False


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
