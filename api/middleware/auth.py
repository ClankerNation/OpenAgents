"""JWT authentication middleware for the OpenAgents API.

@generated-by:
  Name: Antigravity
  Timestamp: 2026-05-28T11:42:51+05:30
  Startup-Configuration: |
    You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
    You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
    The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags.
  Runtime-Info:
    Operating System: mac
    Architecture: arm64
    Home Directory: /Users/himanshujha
    Working Directory: /Users/himanshujha/.gemini/antigravity/scratch/OpenAgents
"""

import jwt
import os
import uuid
import logging
import threading
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback setup - raise immediately at import time in non-development environment
JWT_SECRET = os.getenv("JWT_SECRET")
env = os.getenv("ENV", "development").lower()
is_jwt_secret_fallback = False

if not JWT_SECRET:
    if env == "development":
        JWT_SECRET = "dev_fallback_secret_value_do_not_use_in_production"
        is_jwt_secret_fallback = True
        logger.warning("JWT_SECRET env var is missing. Using development fallback secret.")
    else:
        raise RuntimeError("JWT_SECRET environment variable is missing in non-development environment!")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()


class InMemoryRevocationStore:
    """Thread-safe in-memory store for tracking revoked token JTIs."""
    def __init__(self):
        self._revoked = {}  # jti -> expires_at (datetime)
        self._lock = threading.Lock()

    def revoke(self, jti: str, expires_at: datetime):
        with self._lock:
            self._revoked[jti] = expires_at

    def is_revoked(self, jti: str) -> bool:
        with self._lock:
            if jti not in self._revoked:
                return False
            # Clean up if expired
            if datetime.now(timezone.utc) > self._revoked[jti]:
                del self._revoked[jti]
                return False
            return True


revocation_store = InMemoryRevocationStore()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = to_encode.get("jti") or str(uuid.uuid4())
    to_encode.update({"exp": expire, "iat": now, "type": "access", "jti": jti})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = to_encode.get("jti") or str(uuid.uuid4())
    to_encode.update({"exp": expire, "iat": now, "type": "refresh", "jti": jti})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # Pinned to HS256, explicitly preventing "none" algorithm attacks
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=401, detail="Token is missing unique identifier (jti)")
            
        if revocation_store.is_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
            
        return payload
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def revoke_token(token: str) -> bool:
    """Decodes a token and adds its JTI to the revocation list."""
    try:
        # decode_token already validates the signature, exp, and checks jti presence
        payload = decode_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        # Since decode_token passed, we know exp and jti are valid and present
        expires_at = datetime.fromtimestamp(exp, timezone.utc)
        revocation_store.revoke(jti, expires_at)
        return True
    except HTTPException as e:
        # If it's already expired, consider it effectively revoked/inactive
        if "expired" in str(e.detail).lower():
            return True
        raise e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


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
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
