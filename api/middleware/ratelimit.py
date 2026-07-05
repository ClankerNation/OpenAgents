"""Auth-aware rate limiter."""
import time
from collections import defaultdict

class AuthAwareRateLimiter:
    AUTH_LIMIT = 100  # per minute
    ANON_LIMIT = 10   # per minute
    WINDOW = 60
    
    def __init__(self):
        self.buckets = defaultdict(list)
    
    def check(self, identifier: str, is_authenticated: bool) -> bool:
        now = time.time()
        limit = self.AUTH_LIMIT if is_authenticated else self.ANON_LIMIT
        self.buckets[identifier] = [t for t in self.buckets[identifier] if now - t < self.WINDOW]
        if len(self.buckets[identifier]) >= limit:
            return False
        self.buckets[identifier].append(now)
        return True

rate_limiter = AuthAwareRateLimiter()
