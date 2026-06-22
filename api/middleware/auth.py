"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional, Set

# Graceful fallback: use a development secret if JWT_SECRET is not set
# instead of crashing the entire application
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Token revocation store — keys are JWT jti (JWT ID) values
_revoked_tokens: Set[str] = set()

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


def revoke_token(jti: str) -> None:
    """Revoke a token by its JWT ID. Revoked tokens fail verification."""
    _revoked_tokens.add(jti)


def decode_token(token: str) -> dict:
    try:
        # Pin to HS256 only — reject "none" algorithm attacks
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Check token revocation
    jti = payload.get("jti")
    if jti and jti in _revoked_tokens:
        raise HTTPException(status_code=401, detail="Token has been revoked")

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
    import uuid
    data = {
        "sub": user_id,
        "address": address,
        "roles": roles or [],
        "jti": str(uuid.uuid4()),  # Unique JWT ID for revocation tracking
    }
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def refresh_endpoint(refresh_token: str) -> dict:
    """Handle token refresh with validation."""
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Check revocation
    jti = payload.get("jti")
    if jti and jti in _revoked_tokens:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    # Issue new token pair
    new_data = {
        "sub": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
        "jti": str(__import__("uuid").uuid4()),
    }
    return {
        "token": create_access_token(new_data),
        "refresh_token": create_refresh_token(new_data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
