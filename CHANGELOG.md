# Changelog

All notable changes to the OpenAgents API project will be documented in this file.

## [Unreleased]

### Added
- Added `release_time` column (DateTime, nullable, default datetime.utcnow) and `expired_at` computed property to the `Payment` database model in `api/models/database.py`.
- Implemented `POST /payments/process-expired` endpoint in `api/routes/payments.py` to identify and refund expired escrowed payments, along with a verbatim `@contributor-info` NatSpec block.
- Registered the payments router in `api/main.py` using `app.include_router(payments_router)`.
- Created comprehensive integration test suite `api/test_payments.py` verifying escrow deposit, claim, and process-expired auto-refund flows.
- Updated `package.json` to include `api/test_payments.py` in the npm test script.
- Added `@contributor-info` NatSpec header block to `api/middleware/ratelimit.py`.

### Changed
- Refactored `api/middleware/ratelimit.py` to differentiate rate limiting tiers:
  - 60 req/min for anonymous requests (default fallback).
  - 300 req/min for authenticated requests (successful JWT verification).
  - 1000 req/min for premium API keys (header `x-api-key` containing `"premium"`) or premium JWT tokens (role containing `"premium"`).
  - Retained backwards compatibility with custom `requests_per_window` configs.
  - Implemented `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` header injection on all responses (including 429).
  - Implemented `Retry-After` header injection on 429 responses.
