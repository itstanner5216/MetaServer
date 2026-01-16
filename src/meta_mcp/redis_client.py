"""Shared async Redis client provider and health checks."""

import asyncio
import time
from typing import Any, Optional, Protocol, Tuple

from loguru import logger

from redis import asyncio as aioredis

from .config import Config

_redis_client: Optional[aioredis.Redis] = None
_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_metrics_handler: Optional["RedisMetricsHandler"] = None

_REDIS_SLOW_OPERATION_MS = 100.0


class RedisMetricsHandler(Protocol):
    """Optional metrics sink for Redis operation instrumentation."""

    def timing(self, name: str, value_ms: float, tags: dict[str, str]) -> None:
        """Record a timing metric in milliseconds."""

    def gauge(self, name: str, value: float, tags: dict[str, str]) -> None:
        """Record a gauge metric."""

    def increment(self, name: str, value: int, tags: dict[str, str]) -> None:
        """Increment a counter metric."""


def set_redis_metrics_handler(handler: Optional["RedisMetricsHandler"]) -> None:
    """
    Register a metrics handler for Redis instrumentation.

    This can be used to integrate with Prometheus/StatsD clients without
    introducing a hard dependency in this module.
    """
    global _redis_metrics_handler
    _redis_metrics_handler = handler


def _safe_len(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _get_pool_stats(pool: aioredis.ConnectionPool) -> dict[str, float]:
    in_use = _safe_len(getattr(pool, "_in_use_connections", None))
    available = _safe_len(getattr(pool, "_available_connections", None))
    max_connections = getattr(pool, "max_connections", None)
    total = in_use + available
    utilization = None
    if isinstance(max_connections, int) and max_connections > 0:
        utilization = in_use / max_connections
    return {
        "in_use": float(in_use),
        "available": float(available),
        "total": float(total),
        "max": float(max_connections) if max_connections else 0.0,
        "utilization": float(utilization) if utilization is not None else 0.0,
    }


def _record_metrics(command: str, duration_ms: float, pool: aioredis.ConnectionPool) -> None:
    if _redis_metrics_handler is None:
        return
    tags = {"command": command}
    _redis_metrics_handler.timing("redis.operation.duration_ms", duration_ms, tags)
    _redis_metrics_handler.increment("redis.operation.count", 1, tags)

    pool_stats = _get_pool_stats(pool)
    _redis_metrics_handler.gauge("redis.pool.in_use", pool_stats["in_use"], tags)
    _redis_metrics_handler.gauge("redis.pool.available", pool_stats["available"], tags)
    _redis_metrics_handler.gauge("redis.pool.max", pool_stats["max"], tags)
    _redis_metrics_handler.gauge("redis.pool.utilization", pool_stats["utilization"], tags)


class InstrumentedRedis(aioredis.Redis):
    """Redis client that records timing and pool utilization metrics."""

    async def execute_command(self, *args: Any, **options: Any) -> Any:
        command = "unknown"
        if args:
            command = args[0]
            if isinstance(command, bytes):
                command = command.decode("utf-8", errors="ignore")
            else:
                command = str(command)
        start_time = time.perf_counter()
        try:
            return await super().execute_command(*args, **options)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            _record_metrics(command, duration_ms, self.connection_pool)
            if duration_ms > _REDIS_SLOW_OPERATION_MS:
                logger.warning(
                    "Slow Redis operation detected (command={}, duration_ms={:.2f})",
                    command,
                    duration_ms,
                )


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
                _redis_client = InstrumentedRedis(connection_pool=_redis_pool)
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
