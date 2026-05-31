# API Error Codes

All API errors follow a consistent structured response format.

## Response Schema

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable error description",
  "details": {
    "additional": "context-specific information"
  },
  "request_id": "uuid-for-tracing"
}
```

The `details` field is optional and contains context-specific information about the error.

## Error Codes

### `VALIDATION_ERROR` (HTTP 422)

Request validation failed. The `details` field contains a `validation_errors` array with field-level information.

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {
    "validation_errors": [
      {
        "field": "query.limit",
        "message": "Input should be a valid integer",
        "type": "int_parsing"
      }
    ]
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `NOT_FOUND` (HTTP 404)

The requested resource does not exist.

```json
{
  "code": "NOT_FOUND",
  "message": "Agent not found",
  "details": {
    "agent_id": "abc123"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `AUTH_FAILED` (HTTP 401)

Authentication failed. The request is missing valid credentials or the token is invalid/expired.

```json
{
  "code": "AUTH_FAILED",
  "message": "Token has expired",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `FORBIDDEN` (HTTP 403)

The authenticated user does not have permission to perform this action.

### `RATE_LIMITED` (HTTP 429)

Rate limit exceeded. The `details` field may include `retry_after` in seconds.

```json
{
  "code": "RATE_LIMITED",
  "message": "Rate limit exceeded",
  "details": {
    "retry_after": 30
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `INTERNAL_ERROR` (HTTP 500)

An unexpected server error occurred. Use the `request_id` when reporting issues.

### `BAD_REQUEST` (HTTP 400)

The request was malformed and could not be processed.

### `SERVICE_UNAVAILABLE` (HTTP 503)

The service is temporarily unavailable.

## Request ID

Every request is assigned a unique `request_id`:

- Returned in the `X-Request-ID` response header
- Included in error response bodies
- Clients may provide a custom request ID via the `X-Request-ID` request header (will be preserved)

Use this ID when reporting issues to help with tracing.
