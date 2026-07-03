"""API key management endpoints.

@fix-author
  name: Hermes Agent (dev-nana27)
  date: 2026-07-04
  pre_session_preamble: |
    You are Hermes Agent Bot, an autonomous AI agent operating a solo
    AI-venture company. Your mission is to find and execute high-value
    bounty tasks on GitHub. You operate on a ¥100 token budget with
    7-day survival window.
  runtime:
    os: linux
    arch: x64 (WSL2 on Windows)
    working_dir: /tmp/OpenAgents
    shell: bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ..models.database import get_db, ApiKey
from ..middleware.auth import (
    get_current_user, generate_api_key, _hash_api_key, verify_api_key,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyResponse(BaseModel):
    id: int
    key_prefix: str
    name: Optional[str]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    # Full key only returned on creation
    full_key: Optional[str] = None


class ApiKeyCreateResponse(BaseModel):
    id: int
    key_prefix: str
    name: Optional[str]
    full_key: str
    is_active: bool
    created_at: datetime
    message: str = "Save this key — it will not be shown again"


class ApiKeyGenerateRequest(BaseModel):
    name: Optional[str] = None


class ApiKeyRevokeResponse(BaseModel):
    id: int
    key_prefix: str
    revoked: bool
    message: str = "API key revoked successfully"


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    req: ApiKeyGenerateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a new API key. The full key is returned only once."""
    full_key, key_hash, key_prefix = generate_api_key()

    db_key = ApiKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=req.name,
        user_id=user["id"],
        is_active=True,
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)

    return ApiKeyCreateResponse(
        id=db_key.id,
        key_prefix=key_prefix,
        name=req.name,
        full_key=full_key,
        is_active=True,
        created_at=db_key.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active API keys for the current user (without full keys)."""
    keys = db.query(ApiKey).filter(
        ApiKey.user_id == user["id"],
    ).order_by(ApiKey.created_at.desc()).all()

    return [
        ApiKeyResponse(
            id=k.id,
            key_prefix=k.key_prefix,
            name=k.name,
            is_active=k.is_active,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRevokeResponse)
async def revoke_api_key(
    key_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke an API key. Revoked keys immediately fail authentication."""
    key_record = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == user["id"],
    ).first()

    if not key_record:
        raise HTTPException(status_code=404, detail="API key not found")

    if not key_record.is_active:
        raise HTTPException(status_code=400, detail="API key already revoked")

    key_record.is_active = False
    key_record.revoked_at = datetime.now(timezone.utc)
    db.commit()

    return ApiKeyRevokeResponse(
        id=key_record.id,
        key_prefix=key_record.key_prefix,
        revoked=True,
    )
