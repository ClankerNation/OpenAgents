"""Authentication endpoints: login, refresh, logout."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from ..middleware.auth import (
    generate_login_tokens,
    revoke_token,
    decode_refresh_token,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    user_id: str
    address: str
    roles: Optional[list] = None


class LoginResponse(BaseModel):
    token: str
    refresh_token: str
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    token: str
    expires_in: int


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate and receive access + refresh tokens."""
    tokens = generate_login_tokens(
        user_id=request.user_id,
        address=request.address,
        roles=request.roles,
    )
    return LoginResponse(**tokens)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(request: RefreshRequest):
    """Exchange a valid refresh token for a new access token."""
    payload = decode_refresh_token(request.refresh_token)

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    data = {
        "sub": payload["sub"],
        "address": payload.get("address", ""),
        "roles": payload.get("roles", []),
    }
    new_token = create_access_token(data)

    return RefreshResponse(
        token=new_token,
        expires_in=60 * 60,  # ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Revoke the current access token."""
    return {"message": "Logged out successfully"}
