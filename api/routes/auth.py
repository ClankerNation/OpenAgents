"""API key management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, ApiKey
from ..middleware.auth import get_current_user, generate_api_key, hash_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyCreate(BaseModel):
    name: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: int
    name: Optional[str]
    key: str
    created_at: datetime


class ApiKeyInfo(BaseModel):
    id: int
    name: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]


@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    request: ApiKeyCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    api_key = ApiKey(
        user_id=user["id"],
        key_hash=key_hash,
        name=request.name,
        created_at=datetime.utcnow(),
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    keys = db.query(ApiKey).filter(
        ApiKey.user_id == user["id"],
        ApiKey.revoked == False,
    ).all()
    return [
        ApiKeyInfo(
            id=k.id,
            name=k.name,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == user["id"],
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.revoked = True
    db.commit()
    return {"revoked": True, "id": key_id}
