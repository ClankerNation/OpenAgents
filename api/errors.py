from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

ERROR_CODES = {
    "NOT_FOUND": 1001, "VALIDATION": 1002, "AUTH": 1003,
    "RATE_LIMIT": 1004, "INTERNAL": 1005, "TIMEOUT": 1006,
}

class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = ERROR_CODES.get(code, 0)
        self.message = message
        self.status = status

async def error_handler(req: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}}
    )