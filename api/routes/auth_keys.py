from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import hashlib
import secrets

from ..models.database import get_db, ApiKey
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class ApiKeyCreate(BaseModel):
    label: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: int
    key: str
    label: Optional[str]
    created_at: datetime


@router.get("/api-keys")
async def list_api_keys(user=Depends(get_current_user), db=Depends(get_db)):
    keys = db.query(ApiKey).filter(
        ApiKey.user_id == user["id"], ApiKey.active == True
    ).all()
    return [{"id": k.id, "label": k.label, "created_at": k.created_at} for k in keys]


@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    body: ApiKeyCreate, user=Depends(get_current_user), db=Depends(get_db)
):
    raw_key = f"oa_{secrets.token_hex(24)}"
    key_hash = hash_api_key(raw_key)
    db_key = ApiKey(
        user_id=user["id"],
        key_hash=key_hash,
        label=body.label,
        created_at=datetime.utcnow(),
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    return ApiKeyResponse(
        id=db_key.id, key=raw_key, label=db_key.label, created_at=db_key.created_at
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int, user=Depends(get_current_user), db=Depends(get_db)
):
    key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == user["id"]
    ).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.active = False
    db.commit()
    return {"revoked": True}
