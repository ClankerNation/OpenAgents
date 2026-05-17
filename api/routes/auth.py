from fastapi import APIRouter, Depends
from ..middleware.auth import get_current_user, revoke_token, generate_login_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    return {"message": "Logged out successfully"}


@router.post("/login")
async def login(address: str):
    tokens = generate_login_tokens(str(hash(address)), address, ["user"])
    return tokens


@router.post("/refresh")
async def refresh(user=Depends(get_current_user)):
    tokens = generate_login_tokens(user["id"], user["address"], user["roles"])
    return tokens
