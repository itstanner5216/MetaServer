"""Shared async Redis client provider and health checks."""

import asyncio
from typing import Optional, Tuple

from loguru import logger

from redis import asyncio as aioredis

from .config import Config

_redis_client: Optional[aioredis.Redis] = None
_redis_pool: Optional[aioredis.ConnectionPool] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create a shared Redis client with connection pooling."""
    global _redis_client, _redis_pool

    if _redis_client is None:
        for attempt in range(1, Config.REDIS_CONNECT_RETRIES + 1):
            try:
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
                await _redis_client.ping()
                _log_pool_stats("ready")
                break
            except (aioredis.ConnectionError, aioredis.TimeoutError) as exc:
                logger.warning(
                    "Redis connection attempt {}/{} failed: {}",
                    attempt,
                    Config.REDIS_CONNECT_RETRIES,
                    exc,
                )
                if _redis_client is not None:
                    await _redis_client.close()
                    _redis_client = None
                if _redis_pool is not None:
                    await _redis_pool.disconnect()
                    _redis_pool = None
                if attempt >= Config.REDIS_CONNECT_RETRIES:
                    logger.error("Redis connection retries exhausted")
                    raise
                backoff = min(
                    Config.REDIS_CONNECT_RETRY_DELAY * (2 ** (attempt - 1)),
                    Config.REDIS_CONNECT_RETRY_MAX_DELAY,
                )
                await asyncio.sleep(backoff)
    else:
        _log_pool_stats("reuse")
    return _redis_client


def _log_pool_stats(context: str) -> None:
    if _redis_pool is None:
        return
    in_use = len(_redis_pool._in_use_connections)
    available = len(_redis_pool._available_connections)
    max_connections = _redis_pool.max_connections
    logger.debug(
        "Redis pool {}: in_use={}, idle={}, max={}",
        context,
        in_use,
        available,
        max_connections,
    )


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
