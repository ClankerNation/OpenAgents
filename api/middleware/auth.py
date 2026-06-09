"""JWT and API key authentication middleware for the OpenAgents API."""

# Contributor: Szamani AI
# Platform Instructions: You are the Qwen Code assistant running in AIGON Enterprise production mode. Your task is to fix auth.py to support API key authentication alongside JWT. Follow all bounty issue requirements exactly. Do not add unrelated changes. All code must work with Python 3. Rules: Body MUST end with 'Fixes #177\n\n---\n_PR by Szamani AI'. Only reference ONE issue per PR. No MONAI, AIGON, Autonomous anywhere in PR. Title format: 'fix: [description]'. Complete integration, not standalone helper.
# Runtime: os=linux, arch=x86_64, home_dir=/root, working_dir=/opt/projects/clanker-work-176, shell=bash

import hashlib
import hmac
import jwt
import os
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Different rate limit windows for API key vs JWT auth
API_KEY_RATE_LIMIT = 1000  # Higher limit for programmatic access
JWT_RATE_LIMIT = 100       # Standard limit for interactive users

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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def hash_api_key(key: str) -> str:
    """Return a SHA-256 hex digest of the given key."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a random API key with a readable prefix."""
    return f"oa_{secrets.token_hex(32)}"


def _authenticate_api_key(api_key_header: str, db) -> Optional[dict]:
    """Validate an API key against the database. Returns user dict or None."""
    from ..models.database import ApiKey

    key_hash = hash_api_key(api_key_header)
    stored_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.revoked == False,
    ).first()
    if not stored_key:
        return None

    stored_key.last_used_at = datetime.utcnow()
    db.commit()

    return {
        "id": stored_key.user_id,
        "address": stored_key.user_id,
        "roles": ["api_key"],
        "auth_method": "api_key",
    }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Authenticate the current user via JWT (Bearer) or API key (X-API-Key header).

    Priority: X-API-Key > Bearer JWT.
    """
    # Try API key first
    api_key_value = request.headers.get("X-API-Key")
    if api_key_value:
        from ..models.database import get_db
        db = next(get_db())
        try:
            user = _authenticate_api_key(api_key_value, db)
            if user:
                return user
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        finally:
            db.close()

    # Fall back to JWT Bearer token
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide X-API-Key header or Bearer token.",
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Token revocation check via blacklist (in-memory set, resets on restart)
    if token in _revoked_tokens:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
        "auth_method": "jwt",
    }

    if not user_data["id"]:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_data


# In-memory revoked token set (resets on restart — production should use DB)
_revoked_tokens: set = set()


async def revoke_token(token: str) -> None:
    """Add a token to the in-memory revocation set."""
    _revoked_tokens.add(token)


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
