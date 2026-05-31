"""API key management endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..middleware.auth import (
    generate_api_key_value,
    get_current_jwt_user,
    hash_api_key,
)
from ..models.database import ApiKey, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyCreateRequest(BaseModel):
    name: Optional[str] = None


@router.post("/api-keys")
async def create_api_key(
    body: ApiKeyCreateRequest,
    user=Depends(get_current_jwt_user),
    db=Depends(get_db),
):
    raw_key = generate_api_key_value()
    record = ApiKey(
        user_id=user["id"],
        name=body.name,
        key_hash=hash_api_key(raw_key),
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "name": record.name,
        "api_key": raw_key,
        "created_at": record.created_at.isoformat(),
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user=Depends(get_current_jwt_user),
    db=Depends(get_db),
):
    record = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user["id"], ApiKey.revoked_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="API key not found")
    record.revoked_at = datetime.utcnow()
    db.commit()
    return {"id": key_id, "revoked": True}
