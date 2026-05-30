# Escrow Expiry Auto-Refund Architecture

This document details the architectural changes introduced to support auto-refunding of expired escrow payments.

## Architecture Overview

1. **Database Schema Update ([database.py](file:///Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents/api/models/database.py))**
   - Added a `release_time` field to the `Payment` model: `Column(DateTime, nullable=True, default=datetime.utcnow)`
   - Added a computed property `expired_at` returning `release_time + timedelta(days=30)`.

2. **Endpoint Implementation ([payments.py](file:///Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents/api/routes/payments.py))**
   - Implemented `POST /payments/process-expired`
   - Finds all payments with status `escrowed` that are expired (`expired_at <= datetime.utcnow()`).
   - Updates the status of expired payments to `refunded` (the refund implicitly stays with/goes back to the `from_address` payer).
   - Logs the action using python's standard `logging` with details of timestamp and payment ID.
   - Commits changes to the database.

3. **FastAPI Router Integration ([main.py](file:///Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents/api/main.py))**
   - Imported and registered the payments router `payments_router` on the main FastAPI application instance.

4. **Integration Testing ([test_payments.py](file:///Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents/api/test_payments.py))**
   - Added database integration tests to verify processing expired escrows, verifying the 30-day grace period is respected, status is updated, and logs are emitted.

## Gotchas & Considerations

- **Naive UTC Datetimes:** The database uses `datetime.utcnow()` for default timestamps. These are timezone-naive UTC datetimes. All comparisons are done using `datetime.utcnow()`.
- **SQLAlchemy Property Querying:** Since `expired_at` is a Python property, it cannot be used directly in database-side `.filter()` statements (e.g., `db.query(Payment).filter(Payment.expired_at <= ...)` will fail). To handle this safely, we query all `escrowed` payments and filter them in Python using the `expired_at` property.
- **Idempotency:** The endpoint can be run multiple times safely. Once a payment is updated to `refunded`, it will no longer match the `status == "escrowed"` filter on subsequent invocations.
