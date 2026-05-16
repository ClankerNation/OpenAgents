"""JWT authentication middleware for the OpenAgents API."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET_ENV = "JWT_SECRET"
JWT_ALGORITHM = "HS256"
JWT_DECODE_ALGORITHMS = [JWT_ALGORITHM]
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
REVOKED_TOKEN_IDS: set[str] = set()
REVOKED_TOKENS: set[str] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_jwt_secret() -> str:
    secret = os.getenv(JWT_SECRET_ENV)
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    return secret


def _revocation_key(payload: dict, token: str) -> tuple[set[str], str]:
    token_id = payload.get("jti")
    if token_id:
        return REVOKED_TOKEN_IDS, token_id
    return REVOKED_TOKENS, token


def _revoke_decoded_token(token: str, payload: dict) -> None:
    revoked_set, revoked_value = _revocation_key(payload, token)
    revoked_set.add(revoked_value)


def _ensure_token_not_revoked(token: str, payload: dict) -> None:
    revoked_set, revoked_value = _revocation_key(payload, token)
    if revoked_value in revoked_set:
        raise HTTPException(status_code=401, detail="Token has been revoked")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    secret = get_jwt_secret()
    to_encode = data.copy()
    issued_at = _utcnow()
    expire = issued_at + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": issued_at, "type": "access", "jti": uuid4().hex})
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    secret = get_jwt_secret()
    to_encode = data.copy()
    issued_at = _utcnow()
    expire = issued_at + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": issued_at, "type": "refresh", "jti": uuid4().hex})
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=JWT_DECODE_ALGORITHMS)
        _ensure_token_not_revoked(token, payload)
        return payload
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def revoke_token(token: str) -> dict:
    payload = decode_token(token)
    _revoke_decoded_token(token, payload)
    return payload


def refresh_login_tokens(refresh_token: str) -> dict:
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    _revoke_decoded_token(refresh_token, payload)
    return generate_login_tokens(
        user_id=user_id,
        address=payload.get("address"),
        roles=payload.get("roles", []),
    )


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


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user)):
        if role not in user.get("roles", []):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return role_checker


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    refresh_token = create_refresh_token(data)
    expires_at = int((_utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp())
    return {
        "token": create_access_token(data),
        "refresh_token": refresh_token,
        "refreshToken": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "expiresAt": expires_at,
        "walletAddress": address,
    }
