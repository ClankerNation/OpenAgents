# OpenAgents API Error Codes

All API errors follow a consistent schema:

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable error description",
  "details": { ... },
  "request_id": "uuid-for-tracing"
}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request validation failed (missing/invalid fields) |
| `NOT_FOUND` | 404 | Requested resource does not exist |
| `AUTH_FAILED` | 401 | Authentication failed (invalid/expired token) |
| `FORBIDDEN` | 403 | Authenticated but not authorized for this action |
| `RATE_LIMITED` | 429 | Too many requests, retry after the specified time |
| `BAD_REQUEST` | 400 | Malformed request |
| `CONFLICT` | 409 | Resource conflict (e.g., duplicate entry) |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Error Details

### VALIDATION_ERROR

Includes field-level validation errors:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {
    "fields": {
      "email": "Invalid email format",
      "name": "Field required"
    }
  },
  "request_id": "abc-123"
}
```

### NOT_FOUND

Includes the resource type and identifier:

```json
{
  "code": "NOT_FOUND",
  "message": "Agent not found",
  "details": {
    "resource": "Agent",
    "identifier": "123"
  },
  "request_id": "abc-123"
}
```

### RATE_LIMITED

Includes retry timing:

```json
{
  "code": "RATE_LIMITED",
  "message": "Rate limit exceeded",
  "details": {
    "retry_after": 60
  },
  "request_id": "abc-123"
}
```

Also includes `Retry-After` header.

## Request ID

Every error response includes a `request_id` for tracing:

- Pass `X-Request-ID` header to use your own ID
- If not provided, a UUID is generated
- The ID is returned in both the response body and `X-Request-ID` header

## Example Error Handling (Python)

```python
import requests

response = requests.get("https://api.openagents.dev/agents/999")

if response.status_code != 200:
    error = response.json()
    print(f"Error: {error['code']} - {error['message']}")
    print(f"Request ID: {error['request_id']}")

    if error['code'] == 'NOT_FOUND':
        print(f"Resource: {error['details']['resource']}")
    elif error['code'] == 'VALIDATION_ERROR':
        for field, msg in error['details']['fields'].items():
            print(f"  {field}: {msg}")
```
