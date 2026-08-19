"""
Authentication endpoints for API key management.
@fix-author ARO-Agentic | 2026-08-19
@runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from ..models.database import get_db, ApiKey
from ..middleware.auth import get_current_user, generate_api_key, hash_api_key

router = APIRouter(prefix="/auth", tags=["auth"])

class ApiKeyCreate(BaseModel):
    name: Optional[str] = None

class ApiKeyResponse(BaseModel):
    id: int
    name: Optional[str]
    key: str  # Only returned on creation

class ApiKeyInfo(BaseModel):
    id: int
    name: Optional[str]
    created_at: str
    revoked: bool

@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    payload: ApiKeyCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    db_key = ApiKey(
        user_id=user["id"],
        key_hash=key_hash,
        name=payload.name
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    
    return ApiKeyResponse(
        id=db_key.id,
        name=db_key.name,
        key=raw_key
    )

@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keys = db.query(ApiKey).filter(ApiKey.user_id == user["id"]).all()
    return [
        ApiKeyInfo(
            id=k.id,
            name=k.name,
            created_at=k.created_at.isoformat() if k.created_at else "",
            revoked=bool(k.revoked)
        ) for k in keys
    ]

@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == user["id"]
    ).first()
    
    if not db_key:
        raise HTTPException(status_code=404, detail="API key not found")
        
    db_key.revoked = 1
    db.commit()
    
    return {"status": "revoked", "id": key_id}
