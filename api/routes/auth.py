"""Authentication endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from ..middleware.auth import refresh_access_token, revoke_token
except ImportError:
    from middleware.auth import refresh_access_token, revoke_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    token: str


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    return refresh_access_token(request.refresh_token)


@router.post("/logout")
async def logout(request: LogoutRequest):
    revoke_token(request.token)
    return {"revoked": True}
