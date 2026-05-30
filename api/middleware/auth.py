"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
from fastapi import Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

from ..errors import APIError, ErrorCode

# BUG: No fallback — if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()


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
        raise APIError(
            code=ErrorCode.AUTH_FAILED,
            message="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise APIError(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise APIError(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid token type",
            details={"expected": "access", "got": payload.get("type")},
        )

    # BUG: No token revocation check — logged-out or compromised tokens
    # remain valid until they naturally expire
    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }

    if not user_data["id"]:
        raise APIError(
            code=ErrorCode.AUTH_FAILED,
            message="Invalid token payload",
            details={"reason": "missing subject claim"},
        )

    return user_data


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if role not in user.get("roles", []):
            raise APIError(
                code=ErrorCode.FORBIDDEN,
                message=f"Role '{role}' required",
                details={"required_role": role, "user_roles": user.get("roles", [])},
            )
        return user
    return role_checker


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
