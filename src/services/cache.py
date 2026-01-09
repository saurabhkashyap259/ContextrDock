"""Redis cache service for caching identity resolutions and query results."""

import redis.asyncio as aioredis
from redis import Redis

from src.config import settings


# Global Redis client instance
_redis_client: Redis | None = None
_async_redis_client: aioredis.Redis | None = None


def get_redis_client() -> Redis:
    """Get synchronous Redis client instance.
    
    Returns:
        Redis: Synchronous Redis client
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis_client


async def get_async_redis_client() -> aioredis.Redis:
    """Get asynchronous Redis client instance.
    
    Returns:
        aioredis.Redis: Asynchronous Redis client
    """
    global _async_redis_client
    if _async_redis_client is None:
        _async_redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return _async_redis_client


def close_redis_client():
    """Close Redis client connection."""
    global _redis_client, _async_redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
    if _async_redis_client:
        _async_redis_client.close()
        _async_redis_client = None
