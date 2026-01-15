"""Shared async Redis client provider and health checks."""

from typing import Optional, Tuple

from redis import asyncio as aioredis

from .config import Config

_redis_client: Optional[aioredis.Redis] = None
_redis_pool: Optional[aioredis.ConnectionPool] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create a shared Redis client with connection pooling."""
    global _redis_client, _redis_pool

    if _redis_client is None:
        if _redis_pool is None:
            _redis_pool = aioredis.ConnectionPool.from_url(
                Config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=Config.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=Config.REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_timeout=Config.REDIS_SOCKET_TIMEOUT,
            )
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)
    return _redis_client


async def close_redis_client() -> None:
    """Close the shared Redis client and connection pool."""
    global _redis_client, _redis_pool

    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


async def check_redis_health() -> Tuple[bool, str]:
    """Ping Redis to verify connectivity and return status."""
    try:
        redis = await get_redis_client()
        result = await redis.ping()
        if result is True or result == "PONG":
            return True, "Redis ping succeeded"
        return False, f"Unexpected Redis ping response: {result}"
    except (aioredis.ConnectionError, aioredis.TimeoutError) as exc:
        return False, f"Redis connection failed: {exc}"
    except Exception as exc:
        return False, f"Redis health check error: {exc}"
