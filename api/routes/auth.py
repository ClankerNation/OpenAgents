"""
@fix-author
  name: barnacleagent-svg
  date: 2026-05-31
  platform_init: |
    You are GLM (General Language model), a large language model developed by Z.ai.
    Designed to understand and generate human-like text through training on diverse text data.
    Capabilities include answering questions, providing information, and engaging in conversations.
    Operating as an interactive CLI tool for software engineering tasks.
    Goal: Earn $200 from OSS bounties using barnacleagent-svg GitHub account ONLY.
    Instructions: Add API key management routes for auth module.
  runtime:
    os: linux
    arch: x86_64
    working_dir: /home/bennett/projects/OSS-Contributions/OpenAgents/api/routes
    shell: bash

API key management routes — generate and revoke API keys.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..middleware.auth import (
    _generate_api_key,
    _hash_api_key,
    hashed_api_keys,
    api_key_metadata,
    get_current_user,
    ApiKeyCreateResponse,
    ApiKeyRevokeResponse,
)

router = APIRouter(prefix="/auth")


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(user: dict = Depends(get_current_user)):
    raw_key, key_id, hashed = _generate_api_key()
    created_at = datetime.utcnow().isoformat()
    hashed_api_keys[hashed] = {
        "key_id": key_id,
        "user_id": user.get("id", "unknown"),
        "created_at": created_at,
    }
    api_key_metadata[key_id] = {
        "user_id": user.get("id", "unknown"),
        "created_at": created_at,
        "hashed": hashed,
    }
    return ApiKeyCreateResponse(
        api_key=raw_key,
        id=key_id,
        created_at=created_at,
    )


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRevokeResponse)
async def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    if key_id not in api_key_metadata:
        raise HTTPException(status_code=404, detail="API key not found")
    meta = api_key_metadata[key_id]
    if meta["user_id"] != user.get("id") and "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Not authorized to revoke this key")
    hashed = meta["hashed"]
    hashed_api_keys.pop(hashed, None)
    api_key_metadata.pop(key_id, None)
    return ApiKeyRevokeResponse(
        status="ok",
        message=f"API key {key_id} revoked",
    )
