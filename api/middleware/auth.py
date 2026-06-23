"""JWT authentication middleware for the OpenAgents API.

@fix-author Gaotax2006
@date 2026-06-23
@issue #138 Fix auth.py doesn't support API key authentication alongside session auth
"""

import jwt
import os
import hashlib
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from datetime import datetime, timedelta
from typing import Optional

# BUG: No fallback — if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# API Key configuration
API_KEYS_FILE = os.environ.get("API_KEYS_FILE", "api_keys.txt")

security = HTTPBearer(auto_error=False)
security_basic = HTTPBasic()


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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
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


# --- API Key Authentication ---

def _load_api_keys() -> dict:
    """Load API keys from file. Keys are stored as SHA-256 hashes."""
    keys = {}
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        key_hash, label = parts
                        keys[key_hash] = label
    return keys


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key for secure comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_current_user_or_api_key(request: Request) -> dict:
    """Authenticate via JWT bearer token OR API key header.

    Checks Authorization: Bearer <token> first, then falls back to
    X-API-Key header for API key authentication.
    """
    # Try JWT bearer token first
    creds = await security(request)
    if creds and creds.credentials:
        try:
            payload = decode_token(creds.credentials)
            if payload.get("type") == "access":
                return {
                    "id": payload.get("sub"),
                    "address": payload.get("address"),
                    "roles": payload.get("roles", []),
                    "auth_method": "jwt",
                }
        except HTTPException:
            pass

    # Fall back to API key
    api_key = request.headers.get("x-api-key")
    if api_key:
        key_hash = _hash_api_key(api_key)
        loaded_keys = _load_api_keys()
        if key_hash in loaded_keys:
            return {
                "id": "api:" + loaded_keys[key_hash],
                "address": None,
                "roles": ["api"],
                "auth_method": "api_key",
            }
        raise HTTPException(status_code=401, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Authentication required — provide Bearer token or X-API-Key header")
