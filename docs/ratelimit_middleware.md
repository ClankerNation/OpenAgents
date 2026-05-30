# Rate Limiting Tier Middleware Gotchas & Design

This document details the architecture, design choices, and potential gotchas for the differentiated rate limiting system.

## Tiers & Limits

The `RateLimitMiddleware` dynamically detects three client tiers:
- **Anonymous**: 60 requests/minute. Tracked by client IP (`anon:<ip>`).
- **Authenticated**: 300 requests/minute. Tracked by decoded user ID/sub claim or the token string (`auth:<user_id>`).
- **Premium**: 1000 requests/minute. Tracked by premium key/token or user ID (`premium:<id>`).

## Detections and Logic

1. **API Keys**:
   - The middleware checks for `x-api-key`.
   - If `"premium"` is in the API key value (case-insensitive), it grants the **Premium** tier (1000 req/min).
   - Otherwise, it grants the **Authenticated** tier (300 req/min).

2. **Bearer Tokens (JWT)**:
   - The middleware parses the `Authorization: Bearer <token>` header.
   - It decodes the JWT using `api.middleware.auth.decode_token`.
   - If the token contains `"premium"` or the payload roles/contents include `"premium"`, it grants the **Premium** tier.
   - If the token is valid but doesn't have premium attributes, it grants the **Authenticated** tier.
   - If decoding fails (e.g. invalid signature, expired token), it falls back to **Anonymous** rate limits and allows downstream dependency checks to reject with standard 401s.

## Gotchas

### 1. `JWT_SECRET` KeyError
* **Problem**: `api/middleware/auth.py` reads `os.environ["JWT_SECRET"]` directly on import. If the server or testing suite starts without this variable configured, a `KeyError` crashes the application.
* **Solution**: `ratelimit.py` sets a fallback environment variable (`os.environ["JWT_SECRET"] = "default_secret"`) on startup if it's missing, avoiding imports from throwing runtime KeyErrors.

### 2. Middleware Exceptions in Starlette
* **Problem**: Unhandled exceptions raised during `BaseHTTPMiddleware.dispatch` bypass FastAPI's route exception handlers and cause HTTP 500 errors.
* **Solution**: `RateLimitMiddleware` catches all JWT decoding exceptions inside its handler and gracefully demotes the user to the `anonymous` rate limit bucket.
