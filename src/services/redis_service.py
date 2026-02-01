"""Redis service for task state management."""

import logging
import os
import json
from typing import Optional

import redis.asyncio as redis

from models.responses import TaskResponse

logger = logging.getLogger(__name__)

# Singleton instance
_redis_service: Optional["RedisService"] = None


class RedisService:
    """Manages Redis connections and task state."""

    TASK_PREFIX = "gemini:response:"
    SELECTORS_KEY = "gemini:selectors"
    RATE_LIMIT_PREFIX = "gemini:ratelimit:"
    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
            logger.info(f"Connected to Redis at {self.redis_url}")
        return self._client

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    # Task Management
    async def save_task(self, request_id: str, response: TaskResponse, ttl: int = DEFAULT_TTL):
        """Save task response to Redis."""
        client = await self.connect()
        await client.setex(
            f"{self.TASK_PREFIX}{request_id}",
            ttl,
            response.model_dump_json()
        )
        logger.debug(f"Saved task {request_id} to Redis")

    async def get_task(self, request_id: str) -> Optional[TaskResponse]:
        """Retrieve task response from Redis."""
        client = await self.connect()
        data = await client.get(f"{self.TASK_PREFIX}{request_id}")
        if data:
            return TaskResponse.model_validate_json(data)
        return None

    async def delete_task(self, request_id: str):
        """Delete task from Redis."""
        client = await self.connect()
        await client.delete(f"{self.TASK_PREFIX}{request_id}")

    # Selector Management
    async def get_selectors(self) -> Optional[dict]:
        """Get cached selectors from Redis."""
        client = await self.connect()
        data = await client.get(self.SELECTORS_KEY)
        if data:
            return json.loads(data)
        return None

    async def save_selectors(self, selectors: dict):
        """Save selectors to Redis."""
        client = await self.connect()
        await client.set(self.SELECTORS_KEY, json.dumps(selectors))

    # Rate Limiting
    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.
        Returns (is_allowed, remaining_requests).
        """
        client = await self.connect()
        full_key = f"{self.RATE_LIMIT_PREFIX}{key}"
        
        # Use sliding window counter
        current = await client.get(full_key)
        if current is None:
            await client.setex(full_key, window_seconds, 1)
            return True, max_requests - 1
        
        count = int(current)
        if count >= max_requests:
            return False, 0
        
        await client.incr(full_key)
        return True, max_requests - count - 1

    async def get_rate_limit_remaining(self, key: str, max_requests: int) -> int:
        """Get remaining requests for a rate limit key."""
        client = await self.connect()
        full_key = f"{self.RATE_LIMIT_PREFIX}{key}"
        current = await client.get(full_key)
        if current is None:
            return max_requests
        return max(0, max_requests - int(current))


async def get_redis_service() -> RedisService:
    """Get or create the singleton Redis service."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service
