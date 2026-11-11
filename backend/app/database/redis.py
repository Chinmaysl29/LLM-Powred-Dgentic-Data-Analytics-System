"""Asynchronous Redis adapter with cache primitives and validation."""

import logging

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.app.core.config import Settings
from backend.app.core.exceptions import RedisConnectionError

logger = logging.getLogger(__name__)


class RedisCache:
    """Provide a narrow cache interface for future services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        """Return the initialized Redis client."""
        if self._client is None:
            raise RedisConnectionError("Redis connection has not been initialized")
        return self._client

    async def connect(self) -> None:
        """Create and validate the Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self._settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5.0,
                socket_timeout=5.0,
            )
        try:
            await self._client.ping()
            logger.info("Redis connection established")
        except RedisError as exc:
            await self.close()
            logger.error("Redis connection validation failed: %s", exc.__class__.__name__)
            raise RedisConnectionError("Redis connection validation failed") from None

    async def health_check(self) -> tuple[bool, str]:
        """Ping Redis and return a health result."""
        try:
            if self._client is None:
                await self.connect()
            else:
                await self._client.ping()
            return True, "Redis is reachable"
        except (RedisConnectionError, RedisError, Exception):
            await self.close()
            return False, "Redis is unavailable"

    async def get(self, key: str) -> str | None:
        """Get a cached value by key."""
        try:
            return await self.client.get(key)
        except RedisError as exc:
            raise RedisConnectionError("Redis get operation failed") from exc

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Set a cached value, optionally with a time to live."""
        try:
            return bool(await self.client.set(key, value, ex=ttl_seconds))
        except RedisError as exc:
            raise RedisConnectionError("Redis set operation failed") from exc

    async def delete(self, key: str) -> int:
        """Delete a cached value and return the number of deleted keys."""
        try:
            return await self.client.delete(key)
        except RedisError as exc:
            raise RedisConnectionError("Redis delete operation failed") from exc

    async def delete_matching(self, pattern: str) -> int:
        """Delete a controlled namespace with bounded command/key accumulation.

        SCAN is not a snapshot; concurrent writers retain Redis's usual SCAN
        semantics. A transport failure can occur after earlier batches succeed.
        """
        try:
            deleted = 0
            keys = []
            async for key in self.client.scan_iter(match=pattern, count=200):
                keys.append(key)
                if len(keys) == 200:
                    deleted += int(await self.client.delete(*keys))
                    keys.clear()
            if keys:
                deleted += int(await self.client.delete(*keys))
            return deleted
        except RedisError as exc:
            raise RedisConnectionError("Redis pattern delete operation failed") from exc

    async def push(self, key: str, value: str) -> int:
        """Append a value to a Redis list used by the background job queue."""
        try:
            return int(await self.client.rpush(key, value))
        except RedisError as exc:
            raise RedisConnectionError("Redis queue push operation failed") from exc

    async def pop(self, key: str) -> str | None:
        """Pop the next value from a Redis list without creating another client."""
        try:
            return await self.client.lpop(key)
        except RedisError as exc:
            raise RedisConnectionError("Redis queue pop operation failed") from exc

    async def close(self) -> None:
        """Close the Redis connection pool during shutdown."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Redis connection closed")
