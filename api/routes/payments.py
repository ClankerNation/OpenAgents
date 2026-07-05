"""Payment escrow with expiry validation."""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta

router = APIRouter(prefix="/payments", tags=["payments"])

ESCROW_EXPIRY_HOURS = 24

@router.post("/escrow/{escrow_id}/release")
async def release_escrow(escrow_id: str, created_at: datetime):
    """Release escrow funds with expiry check."""
    elapsed = datetime.now() - created_at
    if elapsed > timedelta(hours=ESCROW_EXPIRY_HOURS):
        raise HTTPException(status_code=400, detail=f"Escrow expired after {ESCROW_EXPIRY_HOURS}h")
    return {"status": "released", "escrow_id": escrow_id}
