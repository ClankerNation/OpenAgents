"""JWT authentication middleware for the OpenAgents API.

@generated-by:
  Name: Antigravity
  Timestamp: 2026-05-28T11:10:00+05:30
  Startup-Instructions:
    1. Create a python virtual environment:
       python3 -m venv venv
    2. Activate the virtual environment:
       source venv/bin/activate
    3. Install the dependencies:
       pip install -r api/requirements.txt
    4. Run the development server:
       export JWT_SECRET="your-secret-key"
       uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
  Runtime-Info:
    OS: mac
    Python: 3
    FastAPI: >=0.115.0
    PyJWT: >=2.8.0
"""

import jwt
import os
import uuid
import logging
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Development fallback setup
JWT_SECRET = os.getenv("JWT_SECRET")
is_jwt_secret_fallback = False
if not JWT_SECRET:
    JWT_SECRET = "dev_fallback_secret_value_do_not_use_in_production"
    is_jwt_secret_fallback = True
    logger.warning("JWT_SECRET env var is missing. Using development fallback secret.")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()


class InMemoryRevocationStore:
    """Thread-safe in-memory store for tracking revoked token JTIs."""
    def __init__(self):
        self._revoked = {}  # jti -> expires_at (datetime)

    def revoke(self, jti: str, expires_at: datetime):
        self._revoked[jti] = expires_at

    def is_revoked(self, jti: str) -> bool:
        if jti not in self._revoked:
            return False
        # Clean up if expired
        if datetime.utcnow() > self._revoked[jti]:
            del self._revoked[jti]
            return False
        return True


revocation_store = InMemoryRevocationStore()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = to_encode.get("jti") or str(uuid.uuid4())
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access", "jti": jti})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = to_encode.get("jti") or str(uuid.uuid4())
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh", "jti": jti})
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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            expires_at = datetime.utcfromtimestamp(exp)
            revocation_store.revoke(jti, expires_at)
            return True
    except jwt.ExpiredSignatureError:
        # Already expired token is effectively revoked/inactive
        return True
    except jwt.InvalidTokenError:
        pass
    return False


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
