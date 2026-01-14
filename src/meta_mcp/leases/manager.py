"""Lease manager implementation (Phase 3)."""

import asyncio
import json
from datetime import datetime, timezone

from loguru import logger
from redis import asyncio as aioredis

from ..config import Config
from .models import ToolLease


class LeaseManager:
    """
    Redis-backed lease manager with automatic TTL expiration.

    Features:
    - Create ephemeral leases with TTL
    - Validate lease existence and expiration
    - Consume lease (decrement calls_remaining)
    - Revoke lease (manual deletion)
    - Purge expired leases (cleanup)

    Security:
    - Leases are scoped to (client_id, tool_id) pairs
    - Redis TTL provides automatic expiration
    - Fail-closed: Returns None on errors
    - Client ID validation prevents cross-session leaks

    Design Plan Section 4.2
    """

    def __init__(self):
        """Initialize lease manager."""
        self._redis_client: aioredis.Redis | None = None
        self._redis_pool: aioredis.ConnectionPool | None = None
        self._notification_callbacks = []  # Phase 8: Client notification callbacks

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
                    Config.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=100,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            self._redis_client = aioredis.Redis(connection_pool=self._redis_pool)
        return self._redis_client

    @staticmethod
    def _lease_key(client_id: str, tool_id: str) -> str:
        """
        Generate Redis key for lease.

        Args:
            client_id: Session identifier
            tool_id: Tool identifier

        Returns:
            Redis key string
        """
        return f"lease:{client_id}:{tool_id}"

    async def grant(
        self,
        client_id: str,
        tool_id: str,
        ttl_seconds: int,
        calls_remaining: int,
        mode_at_issue: str,
        capability_token: str | None = None,
    ) -> ToolLease | None:
        """
        Grant a new lease.

        Creates a lease in Redis with automatic TTL expiration.

        Args:
            client_id: Session identifier (must not be empty)
            tool_id: Tool identifier
            ttl_seconds: Time-to-live in seconds
            calls_remaining: Number of allowed calls
            mode_at_issue: Governance mode when granted
            capability_token: Optional HMAC token for Phase 4

        Returns:
            ToolLease if granted successfully, None on error

        Security:
        - Validates client_id is not empty
        - Fails closed on Redis errors
        """
        # Validate client_id (security-critical)
        if not client_id or not client_id.strip():
            logger.error("Cannot grant lease with empty client_id")
            return None

        try:
            # Create lease
            lease = ToolLease.create(
                client_id=client_id,
                tool_id=tool_id,
                ttl_seconds=ttl_seconds,
                calls_remaining=calls_remaining,
                mode_at_issue=mode_at_issue,
                capability_token=capability_token,
            )

            # Serialize for Redis
            lease_dict = {
                "client_id": lease.client_id,
                "tool_id": lease.tool_id,
                "granted_at": lease.granted_at.isoformat(),
                "expires_at": lease.expires_at.isoformat(),
                "calls_remaining": lease.calls_remaining,
                "mode_at_issue": lease.mode_at_issue,
                "capability_token": lease.capability_token,
            }
            lease_json = json.dumps(lease_dict)

            # Store in Redis with TTL
            redis = await self._get_redis()
            key = self._lease_key(client_id, tool_id)
            await redis.setex(key, ttl_seconds, lease_json)

            logger.info(
                f"Granted lease for {client_id}:{tool_id} "
                f"(TTL={ttl_seconds}s, calls={calls_remaining})"
            )
            return lease

        except ValueError as e:
            logger.error(f"Lease validation failed: {e}")
            return None
        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in grant: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in grant: {e}")
            return None

    async def validate(self, client_id: str, tool_id: str) -> ToolLease | None:
        """
        Validate lease exists and is not expired.

        Args:
            client_id: Session identifier
            tool_id: Tool identifier

        Returns:
            ToolLease if valid, None if not found or expired

        Security:
        - Validates client_id is not empty
        - Fails closed on Redis errors
        - Returns None for invalid/expired leases
        """
        # Validate client_id (security-critical)
        if not client_id or not client_id.strip():
            logger.warning("Cannot validate lease with empty client_id")
            return None

        try:
            redis = await self._get_redis()
            key = self._lease_key(client_id, tool_id)
            lease_json = await redis.get(key)

            if lease_json is None:
                return None

            # Deserialize
            lease_dict = json.loads(lease_json)
            lease = ToolLease(
                client_id=lease_dict["client_id"],
                tool_id=lease_dict["tool_id"],
                granted_at=datetime.fromisoformat(lease_dict["granted_at"]),
                expires_at=datetime.fromisoformat(lease_dict["expires_at"]),
                calls_remaining=lease_dict["calls_remaining"],
                mode_at_issue=lease_dict["mode_at_issue"],
                capability_token=lease_dict.get("capability_token"),
            )

            # Check expiration
            if lease.is_expired():
                logger.warning(f"Lease expired for {client_id}:{tool_id}")
                # Clean up expired lease
                await redis.delete(key)
                return None

            # Check calls remaining
            if not lease.can_consume():
                logger.warning(
                    f"Lease exhausted for {client_id}:{tool_id} "
                    f"(calls_remaining={lease.calls_remaining})"
                )
                return None

            return lease

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in validate: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in validate: {e}")
            return None

    async def consume(self, client_id: str, tool_id: str) -> ToolLease | None:
        """
        Consume one call from lease (decrement calls_remaining).

        Args:
            client_id: Session identifier
            tool_id: Tool identifier

        Returns:
            Updated ToolLease if consumed successfully, None if exhausted

        Security:
        - Validates client_id is not empty
        - Only consumes if lease is valid
        - Deletes lease when calls_remaining reaches 0
        """
        # Validate client_id (security-critical)
        if not client_id or not client_id.strip():
            logger.warning("Cannot consume lease with empty client_id")
            return None

        try:
            redis = await self._get_redis()
            key = self._lease_key(client_id, tool_id)

            # Get current lease
            lease = await self.validate(client_id, tool_id)
            if lease is None:
                return None

            # Decrement calls
            lease.calls_remaining -= 1

            if lease.calls_remaining <= 0:
                # Lease exhausted, delete from Redis
                await redis.delete(key)
                logger.info(f"Lease exhausted and deleted for {client_id}:{tool_id}")
                # Return lease with 0 calls to indicate exhaustion
                return lease
            # Update lease in Redis
            lease_dict = {
                "client_id": lease.client_id,
                "tool_id": lease.tool_id,
                "granted_at": lease.granted_at.isoformat(),
                "expires_at": lease.expires_at.isoformat(),
                "calls_remaining": lease.calls_remaining,
                "mode_at_issue": lease.mode_at_issue,
                "capability_token": lease.capability_token,
            }
            lease_json = json.dumps(lease_dict)

            # Get remaining TTL
            ttl = await redis.ttl(key)
            if ttl > 0:
                await redis.setex(key, ttl, lease_json)
            else:
                # TTL expired, delete
                await redis.delete(key)
                return None

            logger.info(
                f"Consumed lease for {client_id}:{tool_id} (remaining={lease.calls_remaining})"
            )
            return lease

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in consume: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in consume: {e}")
            return None

    async def revoke(self, client_id: str, tool_id: str) -> bool:
        """
        Revoke lease (manual deletion).

        Args:
            client_id: Session identifier
            tool_id: Tool identifier

        Returns:
            True if revoked successfully, False on error

        Security:
        - Validates client_id is not empty
        """
        # Validate client_id (security-critical)
        if not client_id or not client_id.strip():
            logger.error("Cannot revoke lease with empty client_id")
            return False

        try:
            redis = await self._get_redis()
            key = self._lease_key(client_id, tool_id)
            deleted = await redis.delete(key)

            if deleted:
                logger.info(f"Revoked lease for {client_id}:{tool_id}")

            return True

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in revoke: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in revoke: {e}")
            return False

    async def purge_expired(self) -> int:
        """
        Purge expired leases from Redis.

        Note: Redis TTL auto-expires keys, but this method can be used
        for manual cleanup or testing.

        Returns:
            Number of leases purged
        """
        try:
            redis = await self._get_redis()
            expired_keys = []

            # Scan for all lease keys and collect expired ones
            async for key in redis.scan_iter("lease:*"):
                lease_json = await redis.get(key)
                if lease_json is None:
                    continue

                try:
                    lease_dict = json.loads(lease_json)
                    expires_at = datetime.fromisoformat(lease_dict["expires_at"])

                    if datetime.now(timezone.utc) > expires_at:
                        expired_keys.append(key)
                except Exception as e:
                    logger.warning(f"Error parsing lease {key}: {e}")
                    continue

            # Batch delete all expired keys
            purged = 0
            if expired_keys:
                purged = await redis.delete(*expired_keys)
                logger.info(f"Purged {purged} expired leases")

            return purged

        except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
            logger.error(f"Redis connection failed in purge_expired: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error in purge_expired: {e}")
            return 0

    async def close(self):
        """Close Redis connection and pool."""
        if self._redis_client is not None:
            await self._redis_client.close()
            self._redis_client = None
        if self._redis_pool is not None:
            await self._redis_pool.disconnect()
            self._redis_pool = None

    async def _emit_list_changed(self, client_id: str):
        """
        Emit list_changed notification to client (Phase 8).

        This notifies the MCP client that their available tool list has changed,
        triggering a UI refresh or re-fetch of available tools.

        Args:
            client_id: Session identifier for the client to notify
        """
        logger.debug(f"Emitting list_changed notification for client {client_id}")

        # Call registered callbacks
        for callback in self._notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(client_id)
                else:
                    callback(client_id)
            except Exception as e:
                logger.error(f"Error in notification callback: {e}")

    def register_notification_callback(self, callback):
        """
        Register a callback for list_changed notifications (Phase 8).

        Args:
            callback: Async or sync function that takes client_id as parameter
        """
        self._notification_callbacks.append(callback)

    def unregister_notification_callback(self, callback):
        """
        Unregister a notification callback (Phase 8).

        Args:
            callback: Previously registered callback function
        """
        if callback in self._notification_callbacks:
            self._notification_callbacks.remove(callback)


# Module-level singleton
lease_manager = LeaseManager()
