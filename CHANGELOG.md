# Changelog

All notable changes to the OpenAgents API project will be documented in this file.

## [Unreleased]

### Added
- Added `RateLimitMiddleware` to FastAPI app in `api/main.py`.
- Created comprehensive integration test suite `api/test_ratelimit.py` to verify anonymous, authenticated, and premium tier limits, headers, and 429 response behaviors.
- Added `@contributor-info` NatSpec header block to `api/middleware/ratelimit.py`.

### Changed
- Refactored `api/middleware/ratelimit.py` to differentiate rate limiting tiers:
  - 60 req/min for anonymous requests (default fallback).
  - 300 req/min for authenticated requests (successful JWT verification).
  - 1000 req/min for premium API keys (header `x-api-key` containing `"premium"`) or premium JWT tokens (role containing `"premium"`).
  - Retained backwards compatibility with custom `requests_per_window` configs.
  - Implemented `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` header injection on all responses (including 429).
  - Implemented `Retry-After` header injection on 429 responses.
