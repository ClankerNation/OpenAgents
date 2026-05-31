# OpenAgents API Error Codes

All API errors use this schema:

```json
{
  "code": "NOT_FOUND",
  "message": "Agent not found",
  "details": {},
  "request_id": "f77d5c41-8acd-4e48-84dd-64c07da42e2c"
}
```

## Codes

- `VALIDATION_ERROR`: Request payload, path, query, or type validation failed.
- `NOT_FOUND`: Requested resource does not exist.
- `AUTH_FAILED`: Authentication or authorization failed.
- `RATE_LIMITED`: Request throttled by rate limiting.
- `INTERNAL_ERROR`: Unexpected server-side failure.
- `BAD_REQUEST`: Client sent an invalid request.

## Validation Error Details

Validation failures include field-level details:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {
    "fields": {
      "task_id": "Input should be a valid integer"
    }
  },
  "request_id": "abc-123"
}
```
