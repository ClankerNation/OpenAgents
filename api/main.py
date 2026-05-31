import uuid
import logging
from typing import Callable
from fastapi import FastAPI, Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
import contextvars

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request_id_context.set(request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        return response

class RequestIDLogFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_context.get('')
        return True

def setup_logging():
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDLogFilter())
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)