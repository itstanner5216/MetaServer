"""Redis-backed tri-state governance with scoped elevation cache."""

import hashlib
from enum import Enum
from typing import Optional

from loguru import logger
from redis import asyncio as aioredis

from .audit import AuditEvent, audit_logger
from .config import Config
from .governance.session_key import GovernanceKeyManager
from .redis_client import close_redis_client, get_redis_client

# Constants
GOVERNANCE_MODE_KEY = "governance:mode"
ELEVATION_PREFIX = "elevation:"
DEFAULT_ELEVATION_TTL = Config.DEFAULT_ELEVATION_TTL


class ExecutionMode(str, Enum):
    """Tri-state execution mode for governance."""

    READ_ONLY = "read_only"
    PERMISSION = "permission"
    BYPASS = "bypass"


class GovernanceState:
    """Redis-backed governance state manager with scoped elevation cache."""

    def __init__(self):
        """Initialize governance state with lazy Redis connection."""
        self._redis_client: Optional[aioredis.Redis] = None
        self._cached_mode: Optional[ExecutionMode] = None
        self._key_manager = GovernanceKeyManager()
        self._mode_changes_enabled = True

    @staticmethod
    def _parse_mode(mode_value: Optional[str]) -> Optional[ExecutionMode]:
        """Parse execution mode string into ExecutionMode enum."""
        if not mode_value:
            return None
        normalized = mode_value.strip().lower()
        try:
            return ExecutionMode(normalized)
        except ValueError:
            return None

    @classmethod
    def _default_mode(cls) -> ExecutionMode:
        """Resolve default execution mode from configuration."""
        config_value = Config.DEFAULT_EXECUTION_MODE
        parsed_mode = cls._parse_mode(config_value)
        if parsed_mode is None:
            logger.error(
                f"Invalid default governance mode '{config_value}'; using fail-safe default: {ExecutionMode.PERMISSION}"
            )
            return ExecutionMode.PERMISSION
        return parsed_mode

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis client with shared connection pool."""
        self._redis_client = await get_redis_client()
        return self._redis_client

    async def initialize_session_key(self) -> Optional[str]:
        """Generate and persist a new governance session key for this server run."""
        redis = await self._get_redis()
        path = await self._key_manager.initialize(redis)
        return str(path)

    def disable_mode_changes(self) -> None:
        """Disable mode changes until restart (fail-safe)."""
        self._mode_changes_enabled = False

    async def force_mode(self, mode: ExecutionMode) -> bool:
        """Set governance mode without key checks (startup fail-safe path only)."""
        try:
            redis = await self._get_redis()
            await redis.set(GOVERNANCE_MODE_KEY, mode.value)
            self._cached_mode = mode
            return True
        except Exception as e:
            logger.error(f"Failed to force governance mode: {e}")
            return False

    def cleanup_session_key(self) -> None:
        """Clean up session key file on shutdown."""
        self._key_manager.cleanup_key_file()

    async def get_mode(self) -> ExecutionMode:
        """Get current governance mode with fail-safe default."""
        try:
            redis = await self._get_redis()
            mode_str = await redis.get(GOVERNANCE_MODE_KEY)

            if mode_str is None:
                default_mode = self._default_mode()
                logger.warning(
                    f"No governance mode set in Redis, initializing to config default: {default_mode.value}"
                )
                try:
                    await redis.set(GOVERNANCE_MODE_KEY, default_mode.value)
                except Exception as e:
                    logger.error(f"Failed to initialize governance mode in Redis: {e}")
                self._cached_mode = default_mode
                return default_mode

            parsed_mode = self._parse_mode(mode_str)
            if parsed_mode is None:
                default_mode = self._default_mode()
                logger.error(
                    f"Invalid governance mode in Redis: {mode_str}, resetting to config default: {default_mode.value}"
                )
                try:
                    await redis.set(GOVERNANCE_MODE_KEY, default_mode.value)
                except Exception as e:
                    logger.error(f"Failed to reset governance mode in Redis: {e}")
                self._cached_mode = default_mode
                return default_mode
            self._cached_mode = parsed_mode
            return parsed_mode

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(
                f"Redis connection failed in get_mode: {e}, using fail-safe default: {ExecutionMode.PERMISSION}"
            )
            fallback_mode = ExecutionMode.PERMISSION
            self._cached_mode = fallback_mode
            return fallback_mode
        except Exception as e:
            logger.error(
                f"Unexpected error in get_mode: {e}, using fail-safe default: {ExecutionMode.PERMISSION}"
            )
            fallback_mode = ExecutionMode.PERMISSION
            self._cached_mode = fallback_mode
            return fallback_mode

    def get_cached_mode(self) -> ExecutionMode:
        """Get last-known governance mode without awaiting Redis."""
        if self._cached_mode is not None:
            return self._cached_mode
        return self._default_mode()

    async def set_mode(self, mode: ExecutionMode, session_key: str) -> bool:
        """Set governance mode in Redis (requires valid session key)."""
        old_mode = (await self.get_mode()).value

        if not self._mode_changes_enabled:
            audit_logger.log(
                AuditEvent.GOVERNANCE_MODE_CHANGE_DENIED,
                old_mode=old_mode,
                requested_mode=mode.value,
                key_valid=False,
            )
            raise PermissionError("Governance mode changes are disabled until restart")

        try:
            redis = await self._get_redis()
            key_valid = await self._key_manager.validate_and_rotate(session_key, redis)
            if not key_valid:
                audit_logger.log(
                    AuditEvent.GOVERNANCE_MODE_CHANGE_DENIED,
                    old_mode=old_mode,
                    requested_mode=mode.value,
                    key_valid=False,
                )
                raise PermissionError("Invalid governance session key")

            await redis.set(GOVERNANCE_MODE_KEY, mode.value)
            logger.info(f"Governance mode set to: {mode.value}")
            self._cached_mode = mode
            audit_logger.log(
                AuditEvent.GOVERNANCE_MODE_CHANGE,
                old_mode=old_mode,
                requested_mode=mode.value,
                key_valid=True,
            )
            return True
        except PermissionError:
            raise
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in set_mode: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in set_mode: {e}")
            return False

    @staticmethod
    def compute_elevation_hash(tool_name: str, context_key: str, session_id: str) -> str:
        """Compute SHA256 hash for elevation key."""
        composite = f"{tool_name}:{context_key}:{session_id}"
        hash_digest = hashlib.sha256(composite.encode("utf-8")).hexdigest()
        return f"{ELEVATION_PREFIX}{hash_digest}"

    async def grant_elevation(self, hash_key: str, ttl: int = DEFAULT_ELEVATION_TTL) -> bool:
        """Grant elevation for a specific hash key with mandatory TTL."""
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
        """Check if elevation exists for a specific hash key."""
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
        """Revoke elevation for a specific hash key."""
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
        await close_redis_client()
        self._redis_client = None


# Module-level singleton
governance_state = GovernanceState()
