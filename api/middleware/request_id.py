# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:45:50+07:00

import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate a unique request ID (UUID)
        request_id = str(uuid.uuid4())
        # Attach to request.state.request_id
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        # Add X-Request-ID to response headers
        response.headers["X-Request-ID"] = request_id
        return response
