# Walkthrough — Issue #164: Request ID Logging Middleware

## Executive Summary

The OpenAgents API had **no request tracing capability**. Every log line was anonymous, making it impossible to correlate log entries to a specific client request during debugging or incident triage. This patch adds an async-safe `X-Request-ID` middleware backed by Python's `contextvars`, paired with a custom `logging.Filter` that injects the trace token into every log line automatically.

---

## Middleware Architecture

```
Incoming Request
       │
       ▼
┌──────────────────────────────────┐
│     RequestIDMiddleware          │
│                                  │
│  1. Read X-Request-ID header     │
│     ├── present → use as-is      │
│     └── missing → uuid4().hex    │
│                                  │
│  2. request_id_ctx.set(rid)      │
│     (ContextVar — async-safe)    │
│                                  │
│  3. call_next(request)           │
│                                  │
│  4. response.headers             │
│     ["X-Request-ID"] = rid       │
│                                  │
│  5. finally: ctx.reset(token)    │
│     (prevents state leakage)     │
└──────────────────────────────────┘
       │
       ▼
  Route Handler
       │
       ▼
┌──────────────────────────────────┐
│     RequestIDFilter (logging)    │
│                                  │
│  record.request_id =             │
│     request_id_ctx.get("N/A")    │
└──────────────────────────────────┘
       │
       ▼
  Log Output:
  [a1b2c3d4...] INFO - message
```

### Why `contextvars`?

| Approach | Thread-safe | Async-safe | Verdict |
|---|---|---|---|
| `threading.local()` | ✅ | ❌ | Leaks across coroutines sharing a thread |
| Global `dict` keyed by task | ❌ | ❌ | Race conditions; manual cleanup |
| **`contextvars.ContextVar`** | **✅** | **✅** | **Native Python 3.7+ — designed for this** |

---

## Log Format Schema

Every log line emitted through the `openagents` logger follows this format:

```
[%(request_id)s] %(levelname)s - %(message)s
```

| Token | Source | Example |
|---|---|---|
| `%(request_id)s` | `RequestIDFilter` reads `request_id_ctx` | `a1b2c3d4e5f6...` |
| `%(levelname)s` | Standard Python logging | `INFO`, `WARNING`, `ERROR` |
| `%(message)s` | Log call argument | `"Agent 0x... registered"` |

**Sample output:**

```
[8f3a1c92d04b4e7fa3b06712ed5c8e9a] INFO - Health check requested
[8f3a1c92d04b4e7fa3b06712ed5c8e9a] INFO - Returning 42 agents
[N/A] WARNING - Background task ran outside request context
```

---

## Files Changed

| File | Action | Description |
|---|---|---|
| `api/main.py` | Modified | Added `RequestIDMiddleware`, `RequestIDFilter`, `request_id_ctx` ContextVar, and `openagents` logger setup |
| `api/tests/test_logging.py` | Created | 12 pytest cases covering ID generation, client overrides, log filter integration, and isolation |

---

## Environment Variables

No new environment variables are required. The middleware is **zero-config** — it activates automatically on application startup. Clients may optionally send an `X-Request-ID` header to supply their own trace token.

---

## Running the Tests

```bash
# Install dependencies (if not already done)
pip install -r api/requirements.txt

# Run only the request-ID / logging tests
pytest api/tests/test_logging.py -v

# Run the full test suite (includes CORS tests from Issue #166)
pytest api/tests/ -v
```

### Expected Output

```
api/tests/test_logging.py::TestRequestIDPropagation::test_auto_generated_request_id     PASSED
api/tests/test_logging.py::TestRequestIDPropagation::test_unique_ids_per_request         PASSED
api/tests/test_logging.py::TestRequestIDPropagation::test_client_supplied_request_id_preserved PASSED
api/tests/test_logging.py::TestRequestIDPropagation::test_request_id_on_error_route      PASSED
api/tests/test_logging.py::TestClientOverrides::test_arbitrary_client_ids[simple-id]      PASSED
api/tests/test_logging.py::TestClientOverrides::test_arbitrary_client_ids[000...]          PASSED
api/tests/test_logging.py::TestClientOverrides::test_arbitrary_client_ids[UPPER-CASE-ID]  PASSED
api/tests/test_logging.py::TestClientOverrides::test_arbitrary_client_ids[id-with-...]    PASSED
api/tests/test_logging.py::TestClientOverrides::test_arbitrary_client_ids[aaa...]         PASSED
api/tests/test_logging.py::TestClientOverrides::test_empty_header_triggers_generation     PASSED
api/tests/test_logging.py::TestRequestIDFilter::test_filter_adds_request_id_attribute     PASSED
api/tests/test_logging.py::TestRequestIDFilter::test_filter_fallback_outside_request      PASSED
api/tests/test_logging.py::TestRequestIDFilter::test_log_format_includes_request_id       PASSED
api/tests/test_logging.py::TestConcurrentStability::test_sequential_isolation             PASSED
api/tests/test_logging.py::TestConcurrentStability::test_context_reset_after_request      PASSED
```
