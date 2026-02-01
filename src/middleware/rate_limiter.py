"""Rate limiting middleware for the MCP server."""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    
    # Requests per minute for task execution
    tasks_per_minute: int = 10
    
    # Requests per minute for status checks
    status_per_minute: int = 60
    
    # Requests per minute for screenshots
    screenshots_per_minute: int = 20
    
    # Requests per hour for auth refresh
    auth_refresh_per_hour: int = 5
    
    # Global requests per minute (across all endpoints)
    global_per_minute: int = 100


@dataclass
class TokenBucket:
    """Simple token bucket for rate limiting."""
    
    capacity: int
    tokens: float = field(default=0.0)
    last_update: float = field(default_factory=time.time)
    refill_rate: float = field(default=1.0)  # tokens per second
    
    def __post_init__(self):
        self.tokens = float(self.capacity)
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        
        Returns True if tokens were available, False otherwise.
        """
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now
        
        # Refill tokens
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens are available."""
        if self.tokens >= tokens:
            return 0.0
        needed = tokens - self.tokens
        return needed / self.refill_rate


class RateLimiter:
    """
    Rate limiter with per-client and per-endpoint limits.
    
    Uses in-memory token buckets. For distributed systems,
    use RedisService.check_rate_limit() instead.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._buckets: Dict[str, TokenBucket] = {}
    
    def _get_bucket(self, key: str, capacity: int, window_seconds: int = 60) -> TokenBucket:
        """Get or create a token bucket for the given key."""
        if key not in self._buckets:
            refill_rate = capacity / window_seconds
            self._buckets[key] = TokenBucket(
                capacity=capacity,
                refill_rate=refill_rate,
            )
        return self._buckets[key]
    
    def check_task_limit(self, client_id: str = "default") -> bool:
        """
        Check if task execution is allowed for client.
        
        Raises RateLimitExceeded if limit exceeded.
        """
        key = f"tasks:{client_id}"
        bucket = self._get_bucket(key, self.config.tasks_per_minute)
        
        if not bucket.consume():
            wait_time = bucket.get_wait_time()
            logger.warning(f"Rate limit exceeded for tasks. Client: {client_id}")
            raise RateLimitExceeded(
                f"Task rate limit exceeded. Try again in {int(wait_time)} seconds.",
                retry_after=int(wait_time) + 1,
            )
        return True
    
    def check_status_limit(self, client_id: str = "default") -> bool:
        """Check if status check is allowed for client."""
        key = f"status:{client_id}"
        bucket = self._get_bucket(key, self.config.status_per_minute)
        
        if not bucket.consume():
            wait_time = bucket.get_wait_time()
            raise RateLimitExceeded(
                f"Status check rate limit exceeded. Try again in {int(wait_time)} seconds.",
                retry_after=int(wait_time) + 1,
            )
        return True
    
    def check_screenshot_limit(self, client_id: str = "default") -> bool:
        """Check if screenshot is allowed for client."""
        key = f"screenshot:{client_id}"
        bucket = self._get_bucket(key, self.config.screenshots_per_minute)
        
        if not bucket.consume():
            wait_time = bucket.get_wait_time()
            raise RateLimitExceeded(
                f"Screenshot rate limit exceeded. Try again in {int(wait_time)} seconds.",
                retry_after=int(wait_time) + 1,
            )
        return True
    
    def check_auth_refresh_limit(self, client_id: str = "default") -> bool:
        """Check if auth refresh is allowed for client."""
        key = f"auth_refresh:{client_id}"
        # 5 per hour = 3600 seconds window
        bucket = self._get_bucket(key, self.config.auth_refresh_per_hour, window_seconds=3600)
        
        if not bucket.consume():
            wait_time = bucket.get_wait_time()
            raise RateLimitExceeded(
                f"Auth refresh rate limit exceeded. Try again in {int(wait_time)} seconds.",
                retry_after=int(wait_time) + 1,
            )
        return True
    
    def check_global_limit(self) -> bool:
        """Check global rate limit across all clients."""
        key = "global"
        bucket = self._get_bucket(key, self.config.global_per_minute)
        
        if not bucket.consume():
            wait_time = bucket.get_wait_time()
            raise RateLimitExceeded(
                f"Global rate limit exceeded. Server is busy. Try again in {int(wait_time)} seconds.",
                retry_after=int(wait_time) + 1,
            )
        return True
    
    def get_remaining(self, limit_type: str, client_id: str = "default") -> int:
        """Get remaining requests for a limit type."""
        key = f"{limit_type}:{client_id}"
        if key in self._buckets:
            return int(self._buckets[key].tokens)
        
        # Return full capacity if not yet created
        capacity_map = {
            "tasks": self.config.tasks_per_minute,
            "status": self.config.status_per_minute,
            "screenshot": self.config.screenshots_per_minute,
            "auth_refresh": self.config.auth_refresh_per_hour,
        }
        return capacity_map.get(limit_type, 0)
    
    def reset(self, client_id: Optional[str] = None):
        """Reset rate limits for a client or all clients."""
        if client_id:
            keys_to_remove = [k for k in self._buckets if k.endswith(f":{client_id}")]
            for key in keys_to_remove:
                del self._buckets[key]
        else:
            self._buckets.clear()


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the singleton rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
