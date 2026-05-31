"""Authentication routes for API key management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..middleware.auth import (
    generate_api_key,
    get_current_user,
    hash_api_key,
)
from ..models.database import APIKey, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class APIKeyCreateRequest(BaseModel):
    name: str | None = None


@router.post("/api-keys")
async def create_api_key(
    payload: APIKeyCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user_id = int(user["id"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Cannot create API key for this user")

    raw_key = generate_api_key()
    key_record = APIKey(
        user_id=user_id,
        name=payload.name,
        key_hash=hash_api_key(raw_key),
    )
    db.add(key_record)
    db.commit()
    db.refresh(key_record)

    return {"id": key_record.id, "name": key_record.name, "api_key": raw_key}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user_id = int(user["id"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Cannot revoke API key for this user")

    key_record = db.query(APIKey).filter(APIKey.id == key_id, APIKey.user_id == user_id).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(key_record)
    db.commit()
    return {"revoked": True}
