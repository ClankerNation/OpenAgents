# Walkthrough — Issue #172: Graceful In-Memory Fallback for Redis Rate-Limiter Outages

## Executive Summary

The OpenAgents rate limiter (`api/middleware/ratelimit.py`) previously used a naive in-memory fixed-window counter with no external backend and no fault-tolerance layer. A Redis outage — or any future migration to Redis — would result in unhandled exceptions propagating as **500 Internal Server Error** responses to clients.

This patch introduces a **dual-backend rate limiter** with a Redis sorted-set primary layer and a thread-safe in-memory sliding-window fallback. When Redis is unreachable, the middleware seamlessly switches to the local guard without dropping or crashing a single request.

---

## Architecture

```
                   Incoming Request
                         │
                         ▼
              ┌─────────────────────┐
              │  _get_client_ip()   │
              │  (X-Forwarded-For   │
              │   or socket addr)   │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  _is_rate_limited() │
              └──────────┬──────────┘
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
   ┌──────────────────┐    ┌──────────────────┐
   │ RedisRateLimiter  │    │ InMemoryRate     │
   │                   │    │ Limiter          │
   │ Sorted set per IP │    │ deque per IP     │
   │ ZREMRANGEBYSCORE  │    │ threading.Lock   │
   │ ZADD / ZCARD      │    │ sliding window   │
   └────────┬─────────┘    └────────┬─────────┘
            │                       │
            │  ConnectionError?     │
            │  TimeoutError?        │
            │  OSError?             │
            │  ──── fallback ─────► │
            │                       │
            └───────────┬───────────┘
                        │
                        ▼
               (limited, remaining)
                        │
              ┌─────────┴──────────┐
              │                    │
              ▼                    ▼
         429 + Retry-After    200 + headers
                              X-RateLimit-Remaining
                              X-RateLimit-Limit
```

### Redis Backend — Sorted-Set Sliding Window

For each client IP, a Redis sorted set (`ratelimit:<ip>`) stores one member per request with the timestamp as the score:

1. `ZREMRANGEBYSCORE` prunes entries older than the window.
2. `ZADD` inserts the current timestamp.
3. `ZCARD` counts surviving entries.
4. `EXPIRE` sets a TTL equal to the window so stale keys are garbage-collected.

All four operations execute inside a single `pipeline()` for atomicity and round-trip efficiency.

### In-Memory Backend — Deque Sliding Window

Each client IP maps to a `collections.deque` of request timestamps. On every evaluation:

1. Expired entries are popped from the left (`popleft`).
2. The deque length is compared against the limit.
3. If within budget, the current timestamp is appended.

All mutations are serialised under a single `threading.Lock` to guarantee safety across ASGI worker threads.

### Fallback Trigger

```python
try:
    return self._redis_limiter.is_rate_limited(client_ip)
except (ConnectionError, TimeoutError, OSError) as exc:
    logger.warning(
        "Redis unavailable — activating in-memory rate-limit fallback: %s",
        exc,
    )
except Exception as exc:
    logger.warning(
        "Unexpected Redis error — activating in-memory rate-limit fallback: %s",
        exc,
    )
return self._memory_limiter.is_rate_limited(client_ip)
```

The `except` chain catches:
- `ConnectionError` — Redis refused or dropped the connection
- `TimeoutError` — Redis did not respond within the client timeout
- `OSError` — low-level socket failures
- `Exception` — any unexpected redis-py error (defensive catch-all)

A `logger.warning` is emitted on **every** fallback activation so operators can set up alerts.

---

## Files Changed

| File | Action | Description |
|---|---|---|
| `api/middleware/ratelimit.py` | Rewritten | Added `RedisRateLimiter`, `InMemoryRateLimiter`, and resilient `_is_rate_limited` dispatch with try/except fallback |
| `api/tests/test_ratelimit_fallback.py` | Created | 20 pytest cases covering in-memory correctness, Redis failure fallback, mid-flight dropout, warning logs, and integration |

---

## Running the Tests

```bash
# Install dependencies (if not already done)
pip install -r api/requirements.txt

# Run only the rate-limiter fallback tests
pytest api/tests/test_ratelimit_fallback.py -v

# Run the full test suite
pytest api/tests/ -v
```

### Expected Output

```
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_allows_requests_within_limit            PASSED
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_blocks_after_limit_exceeded             PASSED
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_remaining_count_decreases               PASSED
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_separate_ips_tracked_independently      PASSED
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_window_expiry_allows_new_requests       PASSED
api/tests/test_ratelimit_fallback.py::TestInMemoryRateLimiter::test_reset_clears_all_state                  PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_connection_error_triggers_fallback             PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_timeout_error_triggers_fallback                PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_os_error_triggers_fallback                     PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_unexpected_error_triggers_fallback              PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_fallback_warning_logged                        PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_fallback_enforces_limits                       PASSED
api/tests/test_ratelimit_fallback.py::TestRedisFallback::test_no_500_under_sustained_redis_failure           PASSED
api/tests/test_ratelimit_fallback.py::TestMiddlewareIntegration::test_health_endpoint_bypasses_limiter       PASSED
api/tests/test_ratelimit_fallback.py::TestMiddlewareIntegration::test_rate_limit_headers_present             PASSED
api/tests/test_ratelimit_fallback.py::TestMiddlewareIntegration::test_429_includes_retry_after               PASSED
api/tests/test_ratelimit_fallback.py::TestMiddlewareIntegration::test_different_ips_independent              PASSED
api/tests/test_ratelimit_fallback.py::TestMidFlightRedisFailure::test_mid_flight_switch_to_fallback          PASSED
```
