"""Per-session governance key management."""

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from loguru import logger
from redis import asyncio as aioredis

from ..audit import AuditEvent, audit_logger
from ..config import Config

GOVERNANCE_SESSION_KEY_HASH = "governance:session_key_hash"


class GovernanceKeyManager:
    """Manages per-session cryptographic keys for governance mode changes."""

    def __init__(self, key_dir: str | None = None) -> None:
        self.key_dir = Path(key_dir or Config.GOVERNANCE_KEY_DIR)
        self.key_path = self.key_dir / "governance.key"
        self._current_key: str | None = None

    @staticmethod
    def generate_key() -> str:
        """Generate a random 64-character hex session key."""
        return secrets.token_hex(32)

    def write_key(self, key: str) -> Path:
        """Write session key to disk with restrictive permissions."""
        self.key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.key_dir, 0o700)

        self.key_path.write_text(f"{key}\n", encoding="utf-8")
        os.chmod(self.key_path, 0o400)
        self._current_key = key
        return self.key_path

    async def initialize(self, redis: aioredis.Redis) -> Path:
        """Create initial key, persist it, and store only its hash in Redis."""
        key = self.generate_key()
        path = self.write_key(key)
        await redis.set(GOVERNANCE_SESSION_KEY_HASH, self.get_current_key_hash())
        return path

    async def validate_and_rotate(self, provided_key: str, redis: aioredis.Redis) -> bool:
        """Validate the provided key and rotate on successful one-time use."""
        if not self._current_key:
            return False

        is_valid = hmac.compare_digest(provided_key, self._current_key)
        if not is_valid:
            return False

        new_key = self.generate_key()
        self.write_key(new_key)
        await redis.set(GOVERNANCE_SESSION_KEY_HASH, self.get_current_key_hash())
        audit_logger.log(
            AuditEvent.GOVERNANCE_KEY_ROTATED,
            key_valid=True,
        )
        return True

    def get_current_key_hash(self) -> str:
        """Get SHA-256 hash of current key (never returns raw key)."""
        if not self._current_key:
            return ""
        return hashlib.sha256(self._current_key.encode("utf-8")).hexdigest()

    def cleanup_key_file(self) -> None:
        """Delete key file on shutdown if present."""
        try:
            self.key_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning(f"Failed to remove governance key file {self.key_path}: {exc}")
