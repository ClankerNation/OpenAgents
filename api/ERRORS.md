# API error responses

All API errors use the same response envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [],
    "request_id": "7f8b0c3a-1dd2-4efb-83f5-2a4afcb57776"
  }
}
```

`X-Request-ID` is also returned as a response header. Clients may send `X-Request-ID`; otherwise the API generates one.

## Error codes

| Code | HTTP status | Meaning |
|---|---:|---|
| `VALIDATION_ERROR` | 400, 422 | The request body, path, or query parameters are invalid. Validation errors include field-level `details`. |
| `NOT_FOUND` | 404 | The requested resource does not exist. |
| `AUTH_FAILED` | 401, 403 | Authentication failed or the authenticated caller is not authorized. |
| `RATE_LIMITED` | 429 | The caller exceeded the configured request limit. `details.retry_after` gives the retry delay in seconds. |
| `INTERNAL_ERROR` | 500+ | An unexpected server error occurred. |
