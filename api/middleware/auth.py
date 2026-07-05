
# API Key authentication support
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader, HTTPBearer

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(api_key: str = Security(api_key_header), bearer = Security(bearer_scheme)):
    """Authenticate via API Key or JWT Bearer token."""
    if bearer and bearer.credentials:
        return {"type": "bearer", "token": bearer.credentials}
    if api_key:
        return {"type": "api_key", "key": api_key}
    raise HTTPException(status_code=401, detail="Not authenticated")
