"""Authentication routes — API key management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, ApiKey
from ..middleware.auth import get_current_user, generate_api_key, hash_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyResponse(BaseModel):
    id: int
    label: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    active: bool


class ApiKeyCreateResponse(BaseModel):
    id: int
    label: Optional[str]
    api_key: str
    created_at: datetime


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(
    label: Optional[str] = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    raw, key_hash = generate_api_key()
    record = ApiKey(
        user_id=user["id"],
        key_hash=key_hash,
        label=label,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ApiKeyCreateResponse(
        id=record.id,
        label=record.label,
        api_key=raw,
        created_at=record.created_at,
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    record = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == user["id"],
        ApiKey.revoked_at.is_(None),
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="API key not found")
    record.revoked_at = datetime.utcnow()
    db.commit()
    return {"detail": "API key revoked"}


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    records = db.query(ApiKey).filter(
        ApiKey.user_id == user["id"],
    ).all()
    return [
        ApiKeyResponse(
            id=r.id,
            label=r.label,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            active=r.revoked_at is None,
        )
        for r in records
    ]
