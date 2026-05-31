# Error Response Documentation

## Overview

All API errors return a consistent JSON structure with machine-readable error codes, human-readable messages, field-level validation details, and request IDs for tracing.

## Error Response Schema

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable error message",
  "details": {},
  "request_id": "uuid-v4-string"
}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400, 422 | Request validation failed. Check `details.fields` for field-level errors. |
| `NOT_FOUND` | 404 | The requested resource does not exist. |
| `AUTH_FAILED` | 401 | Authentication failed or token is invalid/expired. |
| `FORBIDDEN` | 403 | Authenticated but not authorized to access this resource. |
| `RATE_LIMITED` | 429 | Too many requests. Check `Retry-After` header. |
| `INTERNAL_ERROR` | 500 | An unexpected server error occurred. |

## Examples

### Not Found Error

```json
{
  "code": "NOT_FOUND",
  "message": "Agent not found",
  "details": {
    "agent_id": "nonexistent-id"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Validation Error

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {
    "fields": {
      "query.limit": {
        "message": "ensure this value is less than or equal to 100",
        "type": "value_error.number.not_le"
      }
    }
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

### Rate Limit Error

```json
{
  "code": "RATE_LIMITED",
  "message": "Rate limit exceeded",
  "details": {
    "retry_after": 42
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440002"
}
```

## Request ID

Every response includes an `X-Request-ID` header. This ID is also included in error response bodies for correlation. Clients can provide their own request ID via the `X-Request-ID` request header.

## Field-Level Validation Details

When validation fails, the `details.fields` object contains an entry for each invalid field:

```json
{
  "field.path": {
    "message": "Human-readable validation error",
    "type": "pydantic_error_type"
  }
}
```

Field paths use dot notation (e.g., `query.limit`, `body.name`).
