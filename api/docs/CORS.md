# CORS Configuration Guide

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `ALLOWED_ORIGINS` | Comma-separated list of allowed origins, or `*` for development mode | Empty (deny all) |

## Modes

### Production (explicit origins)
```bash
export ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
```
Credentials are allowed. Only listed origins can access the API.

### Development (wildcard)
```bash
export ALLOWED_ORIGINS="*"
```
All origins allowed. Credentials are NOT permitted with wildcard origin.

### Locked down (no env set)
No origins allowed. Suitable for internal-only or when CORS is handled upstream.
