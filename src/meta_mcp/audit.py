"""Structured JSON audit trail for governance decisions."""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# Constants
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "./audit.jsonl")
AUDIT_RETENTION_DAYS = 30
MAX_CONTENT_LENGTH = 1000  # Truncate large content to prevent log bloat


class AuditEvent(str, Enum):
    """Audit event types for governance decisions."""

    TOOL_INVOKED = "tool_invoked"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_TIMEOUT = "approval_timeout"
    SCOPED_ELEVATION_USED = "scoped_elevation_used"
    SCOPED_ELEVATION_GRANTED = "scoped_elevation_granted"
    ELEVATIONS_REVOKED = "elevations_revoked"
    MODE_CHANGED = "mode_changed"
    BLOCKED_READ_ONLY = "blocked_read_only"
    BYPASS_EXECUTED = "bypass_executed"


class AuditLogger:
    """
    Structured JSON audit logger for governance decisions.

    Features:
    - JSON Lines format (one JSON object per line)
    - ISO 8601 UTC timestamps
    - Automatic content truncation
    - Append-only file mode
    - Comprehensive event tracking
    """

    def __init__(self, log_path: str = None):
        """
        Initialize audit logger with JSON Lines configuration.

        Args:
            log_path: Path to audit log file (defaults to AUDIT_LOG_PATH env var or ./audit.jsonl)
        """
        if log_path is None:
            log_path = os.getenv("AUDIT_LOG_PATH", "./audit.jsonl")
        self.log_path = Path(log_path)
        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _truncate_content(value: Any, max_length: int = MAX_CONTENT_LENGTH) -> Any:
        """
        Truncate large string values to prevent log bloat.

        Args:
            value: Value to potentially truncate
            max_length: Maximum length for string values

        Returns:
            Truncated value if string exceeds max_length, otherwise original value
        """
        if isinstance(value, str) and len(value) > max_length:
            return value[:max_length] + f"... [truncated, {len(value)} total chars]"
        if isinstance(value, dict):
            return {k: AuditLogger._truncate_content(v, max_length) for k, v in value.items()}
        if isinstance(value, list):
            return [AuditLogger._truncate_content(item, max_length) for item in value]
        return value

    def log(self, event: AuditEvent, **kwargs):
        """
        Write structured audit log entry in JSON Lines format.

        Args:
            event: Audit event type
            **kwargs: Additional fields to include in the audit record
        """
        # Create audit record with UTC timestamp
        audit_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event.value,
            **self._truncate_content(kwargs),
        }

        # Serialize to JSON and write directly to file
        json_line = json.dumps(audit_record, ensure_ascii=False)

        # Write directly to audit file (append mode)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json_line + "\n")

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        mode: str,
    ):
        """
        Log tool invocation.

        Args:
            tool_name: Name of the tool being invoked
            arguments: Tool arguments (will be truncated if large)
            session_id: Session identifier
            mode: Current governance mode
        """
        self.log(
            AuditEvent.TOOL_INVOKED,
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
            mode=mode,
        )

    def log_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        approved: bool,
        elevation_ttl: int | None = None,
        request_id: str | None = None,
        selected_scopes: list | None = None,
        lease_seconds: int | None = None,
        error: str | None = None,
        reason: str | None = None,
    ):
        """
        Log approval decision (granted or denied).

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments (will be truncated if large)
            session_id: Session identifier
            approved: Whether approval was granted
            elevation_ttl: TTL for scoped elevation (if granted) - DEPRECATED, use lease_seconds
            request_id: Unique request identifier for traceability
            selected_scopes: List of scopes user approved (if granted)
            lease_seconds: User-specified lease duration in seconds (if granted)
            error: Error message (if decision was ERROR)
            reason: Denial reason (if denied)
        """
        event = AuditEvent.APPROVAL_GRANTED if approved else AuditEvent.APPROVAL_DENIED

        log_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "session_id": session_id,
        }

        # Add request_id for traceability (critical for audit trail)
        if request_id is not None:
            log_data["request_id"] = request_id

        # Add approval-specific fields
        if approved:
            if selected_scopes is not None:
                log_data["selected_scopes"] = selected_scopes
            if lease_seconds is not None:
                log_data["lease_seconds"] = lease_seconds
            # Support legacy elevation_ttl parameter
            elif elevation_ttl is not None:
                log_data["elevation_ttl"] = elevation_ttl
        else:
            # Add denial-specific fields
            if error is not None:
                log_data["error"] = error
            if reason is not None:
                log_data["reason"] = reason

        self.log(event, **log_data)

    def log_approval_timeout(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        timeout_seconds: int,
        request_id: str | None = None,
    ):
        """
        Log approval timeout.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments (will be truncated if large)
            session_id: Session identifier
            timeout_seconds: Timeout duration that was exceeded
            request_id: Unique request identifier for traceability
        """
        log_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "session_id": session_id,
            "timeout_seconds": timeout_seconds,
        }

        # Add request_id for traceability
        if request_id is not None:
            log_data["request_id"] = request_id

        self.log(AuditEvent.APPROVAL_TIMEOUT, **log_data)

    def log_elevation_used(
        self,
        tool_name: str,
        context_key: str,
        session_id: str,
    ):
        """
        Log scoped elevation being used.

        Args:
            tool_name: Name of the tool
            context_key: Context key for the elevation
            session_id: Session identifier
        """
        self.log(
            AuditEvent.SCOPED_ELEVATION_USED,
            tool_name=tool_name,
            context_key=context_key,
            session_id=session_id,
        )

    def log_elevation_granted(
        self,
        tool_name: str,
        context_key: str,
        session_id: str,
        ttl: int,
    ):
        """
        Log scoped elevation being granted.

        Args:
            tool_name: Name of the tool
            context_key: Context key for the elevation
            session_id: Session identifier
            ttl: Time-to-live for the elevation
        """
        self.log(
            AuditEvent.SCOPED_ELEVATION_GRANTED,
            tool_name=tool_name,
            context_key=context_key,
            session_id=session_id,
            ttl=ttl,
        )

    def log_mode_change(
        self,
        old_mode: str,
        new_mode: str,
        changed_by: str,
    ):
        """
        Log governance mode change.

        Args:
            old_mode: Previous governance mode
            new_mode: New governance mode
            changed_by: Identifier of who/what changed the mode
        """
        self.log(
            AuditEvent.MODE_CHANGED,
            old_mode=old_mode,
            new_mode=new_mode,
            changed_by=changed_by,
        )

    def log_blocked(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
        reason: str,
    ):
        """
        Log blocked operation in READ_ONLY mode.

        Args:
            tool_name: Name of the tool that was blocked
            arguments: Tool arguments (will be truncated if large)
            session_id: Session identifier
            reason: Reason for blocking (e.g., "read_only_mode")
        """
        self.log(
            AuditEvent.BLOCKED_READ_ONLY,
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
            reason=reason,
        )

    def log_bypass(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str,
    ):
        """
        Log bypass execution (when mode is BYPASS).

        Args:
            tool_name: Name of the tool executed in bypass mode
            arguments: Tool arguments (will be truncated if large)
            session_id: Session identifier
        """
        self.log(
            AuditEvent.BYPASS_EXECUTED,
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
        )


# Module-level singleton
audit_logger = AuditLogger()
