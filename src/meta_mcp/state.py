"""Redis-backed tri-state governance with scoped elevation cache."""

import hashlib
import os
from enum import Enum
from typing import Optional

from loguru import logger
from redis import asyncio as aioredis

from .config import Config


# Constants
REDIS_URL = Config.REDIS_URL
GOVERNANCE_MODE_KEY = "governance:mode"
ELEVATION_PREFIX = "elevation:"
DEFAULT_ELEVATION_TTL = Config.DEFAULT_ELEVATION_TTL


class ExecutionMode(str, Enum):
    """Tri-state execution mode for governance."""

    READ_ONLY = "read_only"
    PERMISSION = "permission"
    BYPASS = "bypass"


class GovernanceState:
    """
    Redis-backed governance state manager with scoped elevation cache.

    Features:
    - Lazy Redis client initialization
    - Fail-safe mode retrieval (defaults to PERMISSION on Redis failure)
    - Scoped elevation cache with mandatory TTL
    - SHA256-based elevation hash computation
    """

    def __init__(self):
        """Initialize governance state with lazy Redis connection."""
        self._redis_client: Optional[aioredis.Redis] = None
        self._redis_pool: Optional[aioredis.ConnectionPool] = None
        self._redis_url = REDIS_URL

    async def _get_redis(self) -> aioredis.Redis:
        """
        Get or create Redis client with connection pool (lazy initialization).

        Returns:
            Redis client instance with connection pooling
        """
        if self._redis_client is None:
            # Create connection pool if not exists
            if self._redis_pool is None:
                self._redis_pool = aioredis.ConnectionPool.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=100,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            self._redis_client = aioredis.Redis(connection_pool=self._redis_pool)
        return self._redis_client

    async def get_mode(self) -> ExecutionMode:
        """
        Get current governance mode with fail-safe default.

        FAIL-SAFE: Returns PERMISSION if Redis is unreachable.
        This ensures the system requires explicit approval even during failures,
        never defaulting to BYPASS which would be a security risk.

        Returns:
            Current execution mode, or PERMISSION if Redis fails
        """
        try:
            redis = await self._get_redis()
            mode_str = await redis.get(GOVERNANCE_MODE_KEY)

            if mode_str is None:
                # No mode set, return fail-safe default
                logger.warning(
                    f"No governance mode set in Redis, using fail-safe default: {ExecutionMode.PERMISSION}"
                )
                return ExecutionMode.PERMISSION

            # Validate and return mode
            try:
                return ExecutionMode(mode_str)
            except ValueError:
                logger.error(
                    f"Invalid governance mode in Redis: {mode_str}, using fail-safe default: {ExecutionMode.PERMISSION}"
                )
                return ExecutionMode.PERMISSION

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(
                f"Redis connection failed in get_mode: {e}, using fail-safe default: {ExecutionMode.PERMISSION}"
            )
            return ExecutionMode.PERMISSION
        except Exception as e:
            logger.error(
                f"Unexpected error in get_mode: {e}, using fail-safe default: {ExecutionMode.PERMISSION}"
            )
            return ExecutionMode.PERMISSION

    async def set_mode(self, mode: ExecutionMode) -> bool:
        """
        Set governance mode in Redis.

        Args:
            mode: Execution mode to set

        Returns:
            True if mode was set successfully, False otherwise
        """
        try:
            redis = await self._get_redis()
            await redis.set(GOVERNANCE_MODE_KEY, mode.value)
            logger.info(f"Governance mode set to: {mode.value}")
            return True
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in set_mode: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in set_mode: {e}")
            return False

    @staticmethod
    def compute_elevation_hash(
        tool_name: str, context_key: str, session_id: str
    ) -> str:
        """
        Compute SHA256 hash for elevation key.

        Creates a unique hash based on tool name, context, and session
        to ensure elevation grants are scoped appropriately.

        Args:
            tool_name: Name of the tool requesting elevation
            context_key: Context identifier (e.g., file path, resource)
            session_id: Session identifier

        Returns:
            SHA256 hex digest prefixed with ELEVATION_PREFIX
        """
        composite = f"{tool_name}:{context_key}:{session_id}"
        hash_digest = hashlib.sha256(composite.encode("utf-8")).hexdigest()
        return f"{ELEVATION_PREFIX}{hash_digest}"

    async def grant_elevation(
        self, hash_key: str, ttl: int = DEFAULT_ELEVATION_TTL
    ) -> bool:
        """
        Grant elevation for a specific hash key with mandatory TTL.

        Args:
            hash_key: Elevation hash key (from compute_elevation_hash)
            ttl: Time-to-live in seconds (mandatory, default: 300)

        Returns:
            True if elevation was granted, False otherwise
        """
        if ttl <= 0:
            logger.error(f"Invalid TTL for elevation grant: {ttl}")
            return False

        try:
            redis = await self._get_redis()
            await redis.setex(hash_key, ttl, "granted")
            logger.info(f"Elevation granted for {hash_key} with TTL {ttl}s")
            return True
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in grant_elevation: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in grant_elevation: {e}")
            return False

    async def check_elevation(self, hash_key: str) -> bool:
        """
        Check if elevation exists for a specific hash key.

        Args:
            hash_key: Elevation hash key (from compute_elevation_hash)

        Returns:
            True if elevation exists, False otherwise
        """
        try:
            redis = await self._get_redis()
            exists = await redis.exists(hash_key)
            return bool(exists)
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in check_elevation: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in check_elevation: {e}")
            return False

    async def revoke_elevation(self, hash_key: str) -> bool:
        """
        Revoke elevation for a specific hash key.

        Args:
            hash_key: Elevation hash key (from compute_elevation_hash)

        Returns:
            True if elevation was revoked (or didn't exist), False on error
        """
        try:
            redis = await self._get_redis()
            deleted = await redis.delete(hash_key)
            if deleted:
                logger.info(f"Elevation revoked for {hash_key}")
            return True
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in revoke_elevation: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in revoke_elevation: {e}")
            return False

    async def close(self):
        """Close Redis connection and pool."""
        if self._redis_client is not None:
            await self._redis_client.close()
            self._redis_client = None
        if self._redis_pool is not None:
            await self._redis_pool.disconnect()
            self._redis_pool = None


# Module-level singleton
governance_state = GovernanceState()
