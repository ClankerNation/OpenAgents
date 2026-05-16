"""Authentication token endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

try:
    from ..middleware.auth import refresh_login_tokens, revoke_token
except ImportError:  # pragma: no cover - supports `cd api && uvicorn main:app`
    if __package__ and __package__.startswith("api"):
        raise
    from middleware.auth import refresh_login_tokens, revoke_token


router = APIRouter(prefix="/auth", tags=["auth"])
optional_security = HTTPBearer(auto_error=False)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(alias="refreshToken")


class RevokeRequest(BaseModel):
    token: Optional[str] = None


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    return refresh_login_tokens(request.refresh_token)


@router.post("/revoke")
async def revoke_auth_token(
    request: Optional[RevokeRequest] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
):
    token = request.token if request and request.token else None
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    payload = revoke_token(token)
    return {"revoked": True, "type": payload.get("type")}
