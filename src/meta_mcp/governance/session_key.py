"""Per-session governance key management."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Optional

from loguru import logger
from redis import asyncio as aioredis

from ..config import Config


GOVERNANCE_SESSION_KEY_HASH_KEY = "governance:session_key_hash"


class GovernanceKeyManager:
    """Manages one-time governance session keys for mode changes."""

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._current_key: Optional[str] = None

    @staticmethod
    def generate_key() -> str:
        """Generate a cryptographically secure 64-character hex key."""
        return secrets.token_hex(32)

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def write_key(self, key: str) -> Path:
        """Write the governance key to disk with owner-read-only permissions."""
        key_dir = Path(Config.GOVERNANCE_KEY_DIR)
        key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(key_dir, 0o700)

        key_path = key_dir / "governance.key"
        key_path.write_text(key, encoding="utf-8")
        os.chmod(key_path, 0o400)
        self._current_key = key
        return key_path

    async def initialize(self) -> Path:
        """Generate initial key, persist it, and store only hash in Redis."""
        key = self.generate_key()
        path = self.write_key(key)
        await self._redis.set(GOVERNANCE_SESSION_KEY_HASH_KEY, self._hash_key(key))
        return path

    async def validate_and_rotate(self, provided_key: str) -> bool:
        """Validate provided key and rotate to a new key when valid."""
        current_hash = await self._redis.get(GOVERNANCE_SESSION_KEY_HASH_KEY)
        provided_hash = self._hash_key(provided_key)

        if not current_hash or not hmac.compare_digest(current_hash, provided_hash):
            return False

        new_key = self.generate_key()
        self.write_key(new_key)
        await self._redis.set(GOVERNANCE_SESSION_KEY_HASH_KEY, self._hash_key(new_key))
        logger.info("Governance session key rotated after successful mode change")
        return True

    async def get_current_key_hash(self) -> str:
        """Return the current key hash stored in Redis."""
        key_hash = await self._redis.get(GOVERNANCE_SESSION_KEY_HASH_KEY)
        return key_hash or ""

    def cleanup(self) -> None:
        """Delete governance key file from disk during shutdown."""
        key_path = Path(Config.GOVERNANCE_KEY_DIR) / "governance.key"
        if key_path.exists():
            key_path.unlink()
