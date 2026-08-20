"""Rate limiting middleware for the OpenAgents API.

@contributor Claude Fable 5 (Autonomous Agent)
@platform [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
@date 2026-08-20T12:25:00Z
"""

import time
import json
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional, List

# Try to import redis for persistent storage, fallback to SQLite
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


# Per-endpoint configuration registry
_ENDPOINT_CONFIGS: Dict[str, RateLimitConfig] = {}

def set_endpoint_limit(path_prefix: str, config: RateLimitConfig):
    """Configure rate limits for specific endpoint prefixes."""
    _ENDPOINT_CONFIGS[path_prefix] = config


class PersistentStore:
    """Abstract base for persistent rate limit storage."""
    
    def record_request(self, key: str, timestamp: float, window_seconds: int) -> int:
        """Record a request and return count within window."""
        raise NotImplementedError
    
    def get_count(self, key: str, window_seconds: int) -> int:
        """Get current request count within window."""
        raise NotImplementedError


class RedisStore(PersistentStore):
    """Redis-backed sliding window rate limiter using sorted sets."""
    
    def __init__(self, url: str = "redis://localhost:6379"):
        self.client = redis.from_url(url, decode_responses=True)
    
    def record_request(self, key: str, timestamp: float, window_seconds: int) -> int:
        pipe = self.client.pipeline()
        window_start = timestamp - window_seconds
        
        # Remove old entries outside window
        pipe.zremrangebyscore(key, 0, window_start)
        # Add new request with timestamp as score
        pipe.zadd(key, {f"{timestamp}:{os.urandom(4).hex()}": timestamp})
        # Set expiry to auto-cleanup
        pipe.expire(key, window_seconds + 10)
        # Get count in current window
        pipe.zcard(key)
        
        results = pipe.execute()
        return results[-1]
    
    def get_count(self, key: str, window_seconds: int) -> int:
        window_start = time.time() - window_seconds
        self.client.zremrangebyscore(key, 0, window_start)
        return self.client.zcard(key)


class SQLiteStore(PersistentStore):
    """SQLite-backed sliding window rate limiter for environments without Redis."""
    
    def __init__(self, db_path: str = "/tmp/ratelimit.db"):
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT,
                timestamp REAL,
                PRIMARY KEY (key, timestamp)
            )
        """)
        self.conn.commit()
    
    def record_request(self, key: str, timestamp: float, window_seconds: int) -> int:
        import sqlite3
        window_start = timestamp - window_seconds
        
        cursor = self.conn.cursor()
        # Cleanup old entries
        cursor.execute("DELETE FROM rate_limits WHERE key=? AND timestamp<?", (key, window_start))
        # Insert new entry
        cursor.execute("INSERT OR REPLACE INTO rate_limits (key, timestamp) VALUES (?, ?)", (key, timestamp))
        # Count current window
        cursor.execute("SELECT COUNT(*) FROM rate_limits WHERE key=? AND timestamp>=?", (key, window_start))
        count = cursor.fetchone()[0]
        self.conn.commit()
        return count
    
    def get_count(self, key: str, window_seconds: int) -> int:
        window_start = time.time() - window_seconds
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rate_limits WHERE key=? AND timestamp>=?", (key, window_start))
        return cursor.fetchone()[0]


class InMemoryStore(PersistentStore):
    """Fallback in-memory store with sliding window (not persistent across restarts)."""
    
    def __init__(self):
        self._data: Dict[str, List[float]] = defaultdict(list)
    
    def record_request(self, key: str, timestamp: float, window_seconds: int) -> int:
        window_start = timestamp - window_seconds
        # Prune old entries
        self._data[key] = [t for t in self._data[key] if t >= window_start]
        self._data[key].append(timestamp)
        return len(self._data[key])
    
    def get_count(self, key: str, window_seconds: int) -> int:
        window_start = time.time() - window_seconds
        return len([t for t in self._data.get(key, []) if t >= window_start])


def _create_store() -> PersistentStore:
    """Create the best available persistent store."""
    redis_url = os.environ.get("REDIS_URL")
    if REDIS_AVAILABLE and redis_url:
        try:
            store = RedisStore(redis_url)
            store.client.ping()
            return store
        except Exception:
            pass
    
    # Fallback to SQLite
    try:
        return SQLiteStore()
    except Exception:
        # Ultimate fallback
        return InMemoryStore()


# Global persistent store instance
_store: PersistentStore = _create_store()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.default_config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with trusted proxy validation.
        
        Only trusts X-Forwarded-For if request comes from localhost/private network.
        Otherwise uses direct connection IP to prevent header spoofing.
        """
        client_host = request.client.host if request.client else "unknown"
        
        # Only trust forwarded headers from trusted proxies (localhost/private)
        trusted_prefixes = ("127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", 
                           "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                           "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
                           "192.168.", "::1", "fc00:", "fd00:")
        
        is_trusted_proxy = any(client_host.startswith(p) for p in trusted_prefixes)
        
        if is_trusted_proxy:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                # Take the leftmost (original client) IP
                return forwarded.split(",")[0].strip()
        
        return client_host

    def _get_config_for_path(self, path: str) -> RateLimitConfig:
        """Get rate limit config for endpoint, falling back to default."""
        for prefix, config in _ENDPOINT_CONFIGS.items():
            if path.startswith(prefix):
                return config
        return self.default_config

    def _is_rate_limited(self, client_ip: str, path: str) -> Tuple[bool, int, int]:
        """Check rate limit using sliding window. Returns (limited, remaining, retry_after)."""
        global _store
        
        config = self._get_config_for_path(path)
        key = f"rl:{client_ip}:{path}"
        now = time.time()
        
        try:
            count = _store.record_request(key, now, config.window_seconds)
        except Exception:
            # If store fails, allow request but log error
            return False, config.requests_per_window, 0
        
        if count > config.requests_per_window:
            # Calculate retry_after based on oldest entry in window
            retry_after = config.window_seconds
            return True, 0, retry_after
        
        remaining = max(0, config.requests_per_window - count)
        return False, remaining, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        path = request.url.path
        
        is_limited, remaining, retry_after = self._is_rate_limited(client_ip, path)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        config = self._get_config_for_path(path)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(config.requests_per_window)
        response.headers["X-RateLimit-Window"] = str(config.window_seconds)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
