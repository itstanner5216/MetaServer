"""Data models for tool leases (Phase 3)."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class ToolLease:
    """
    Ephemeral tool lease with expiration and call accounting.

    Leases are scoped to (client_id, tool_id) pairs and stored in Redis
    with automatic TTL expiration.

    Security Invariants:
    - client_id must not be empty (session isolation)
    - ttl_seconds must be > 0 (leases must expire)
    - calls_remaining must be >= 0 (cannot be negative)
    - expires_at must be > granted_at (time must flow forward)

    Design Plan Section 4.1
    """

    client_id: str
    tool_id: str
    granted_at: datetime
    expires_at: datetime
    calls_remaining: int
    mode_at_issue: str  # "READ_ONLY", "PERMISSION", "BYPASS"
    capability_token: Optional[str] = None  # Phase 4 integration

    @classmethod
    def create(
        cls,
        client_id: str,
        tool_id: str,
        ttl_seconds: int,
        calls_remaining: int,
        mode_at_issue: str,
        capability_token: Optional[str] = None,
    ) -> "ToolLease":
        """
        Create a new ToolLease with validation.

        Args:
            client_id: Session identifier (must not be empty)
            tool_id: Tool identifier
            ttl_seconds: Time-to-live in seconds (must be > 0)
            calls_remaining: Number of allowed calls (must be >= 0)
            mode_at_issue: Governance mode when lease granted
            capability_token: Optional HMAC token for Phase 4

        Returns:
            New ToolLease instance

        Raises:
            ValueError: If any validation fails
        """
        # Validate client_id
        if not client_id or not client_id.strip():
            raise ValueError("client_id must not be empty")

        # Validate TTL
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")

        # Validate calls_remaining
        if calls_remaining < 0:
            raise ValueError(f"calls_remaining must be >= 0, got {calls_remaining}")

        # Validate tool_id
        if not tool_id or not tool_id.strip():
            raise ValueError("tool_id must not be empty")

        # Compute timestamps
        granted_at = datetime.now(timezone.utc)
        expires_at = granted_at + timedelta(seconds=ttl_seconds)

        return cls(
            client_id=client_id,
            tool_id=tool_id,
            granted_at=granted_at,
            expires_at=expires_at,
            calls_remaining=calls_remaining,
            mode_at_issue=mode_at_issue,
            capability_token=capability_token,
        )

    def is_expired(self) -> bool:
        """
        Check if lease has expired.

        Returns:
            True if current time > expires_at
        """
        return datetime.now(timezone.utc) > self.expires_at

    def can_consume(self) -> bool:
        """
        Check if lease can be consumed.

        A lease can be consumed if:
        1. It is not expired
        2. It has calls remaining

        Returns:
            True if lease can be consumed
        """
        return not self.is_expired() and self.calls_remaining > 0
