"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request
from datetime import datetime, timedelta
from typing import Optional

# BUG: No fallback — if JWT_SECRET is not set, os.environ[] raises KeyError
# crashing the entire application on startup
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)
API_KEYS: dict = {}


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
    if not credentials:
        api_key = credentials.request.headers.get("X-API-Key") if credentials and credentials.request else None
        if not api_key:
            raise HTTPException(status_code=401, detail="Not authenticated")
        import hashlib
        hashed = hashlib.sha256(api_key.encode()).hexdigest()
        if hashed not in API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid API key")
        key_data = API_KEYS[hashed]
        return {"id": key_data["user_id"], "address": key_data["address"], "roles": key_data.get("roles", [])}
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


from fastapi import APIRouter
auth_router = APIRouter(prefix="/auth", tags=["auth"])

@auth_router.post("/api-keys")
async def create_api_key(user: dict = Depends(get_current_user)):
    import secrets, hashlib
    api_key = secrets.token_hex(32)
    hashed = hashlib.sha256(api_key.encode()).hexdigest()
    API_KEYS[hashed] = {"user_id": user["id"], "address": user["address"], "roles": user.get("roles", [])}
    return {"api_key": api_key}

@auth_router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    global API_KEYS
    hashed_keys = list(API_KEYS.keys())
    for hk in hashed_keys:
        if API_KEYS[hk]["user_id"] == user["id"] and hk == key_id:
            del API_KEYS[hk]
            return {"revoked": True}
    raise HTTPException(status_code=404, detail="Key not found")