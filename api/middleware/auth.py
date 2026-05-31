"""JWT and API key authentication middleware for the OpenAgents API."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..models.database import APIKey, get_db

# BUG: No fallback — if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)


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


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def authenticate_api_key(raw_key: str, db: Session) -> Optional[dict]:
    key_hash = hash_api_key(raw_key)
    key_record = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
    if not key_record:
        return None

    user = key_record.user
    return {
        "id": str(key_record.user_id),
        "address": getattr(user, "address", None),
        "roles": [],
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    raw_api_key = request.headers.get("X-API-Key")
    if raw_api_key:
        user_data = authenticate_api_key(raw_api_key, db)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user_data

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # BUG: No token revocation check — logged-out or compromised tokens
    # remain valid until they naturally expire
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
