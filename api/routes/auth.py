"""Authentication endpoints for JWT users and generated API keys.

Contributor: Codex for charlie12520.
Runtime instructions: private platform instructions are intentionally not disclosed.
Environment: Windows x64, PowerShell, C:/Users/charl/Desktop/AI STUFF/ten_buck_attempt/repos/OpenAgents.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..middleware.auth import generate_api_key, get_current_user, hash_api_key
from ..models.database import ApiKey, User, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class ApiKeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=128)


def _get_or_create_user(db, user_context: dict) -> User:
    user_id = user_context.get("id")
    address = user_context.get("address")

    user = None
    if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
        user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None and address:
        user = db.query(User).filter(User.address == address).first()
    if user is not None:
        return user
    if not address:
        raise HTTPException(status_code=401, detail="Authenticated user has no address")

    user = User(address=address)
    if isinstance(user_id, str) and user_id.isdigit():
        user.id = int(user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _require_jwt_session(user_context: dict) -> None:
    if user_context.get("auth_method") != "jwt":
        raise HTTPException(status_code=403, detail="JWT authentication required")


@router.post("/api-keys")
async def create_api_key(
    request: ApiKeyCreate,
    user_context=Depends(get_current_user),
    db=Depends(get_db),
):
    _require_jwt_session(user_context)
    user = _get_or_create_user(db, user_context)
    raw_key = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        name=request.name,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:12],
        created_at=datetime.utcnow(),
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": api_key.key_prefix,
    }


@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(
    api_key_id: int,
    user_context=Depends(get_current_user),
    db=Depends(get_db),
):
    _require_jwt_session(user_context)
    user = _get_or_create_user(db, user_context)
    api_key = (
        db.query(ApiKey)
        .filter(
            ApiKey.id == api_key_id,
            ApiKey.user_id == user.id,
            ApiKey.revoked_at.is_(None),
        )
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.revoked_at = datetime.utcnow()
    db.commit()
    return {"id": api_key.id, "revoked": True}
