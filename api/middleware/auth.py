"""JWT authentication middleware for the OpenAgents API.

@generated-by: chico10117
@generated-at: 2026-08-05T15:08:01Z
@runtime: macOS arm64, working_dir=/tmp/openagents-auth-rework, shell=zsh
@platform-instructions: private session material intentionally omitted
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# A missing development secret should not prevent the API from importing. An
# ephemeral fallback avoids shipping a reusable signing secret; operators must
# set JWT_SECRET in deployments where tokens need to survive a restart.
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET is not set; using an ephemeral development signing secret"
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
revoked_tokens: set[str] = set()
_revocation_lock = RLock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _encode_token(
    data: dict,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    to_encode = data.copy()
    now = _utcnow()
    to_encode.update(
        {
            "exp": now + expires_delta,
            "iat": now,
            "jti": uuid4().hex,
            "type": token_type,
        }
    )
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str, verify_exp: bool = True) -> dict:
    options = {"verify_exp": verify_exp}
    if verify_exp:
        options["require"] = ["exp", "iat", "jti", "type"]
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return payload


def _is_revoked(jti: Optional[str]) -> bool:
    with _revocation_lock:
        return bool(jti) and jti in revoked_tokens


def _revoke_jti(jti: Optional[str]) -> str:
    if not jti:
        raise HTTPException(status_code=401, detail="Token has no revocation ID")
    with _revocation_lock:
        revoked_tokens.add(jti)
    return jti


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _encode_token(
        data,
        "access",
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(data: dict) -> str:
    return _encode_token(
        data,
        "refresh",
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    payload = _decode_token(token)
    if _is_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    return payload


def revoke_token(token: str) -> str:
    """Revoke a signed token by its unique JWT ID."""
    payload = _decode_token(token, verify_exp=False)
    return _revoke_jti(payload.get("jti"))


def refresh_access_token(refresh_token: str) -> dict:
    """Issue a new access token only from a valid, non-revoked refresh token."""
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token type")

    identity = {
        key: payload[key]
        for key in ("sub", "address", "roles")
        if key in payload
    }
    if not identity.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")
    # Rotate the refresh token so a stolen token cannot be replayed after use.
    _revoke_jti(payload.get("jti"))
    return generate_login_tokens(
        identity["sub"],
        identity.get("address", ""),
        identity.get("roles", []),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # decode_token performs signature, expiry, and revocation checks first.
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
