"""Tests for audit log rotation and retention cleanup."""

from datetime import datetime, timedelta, timezone

from src.meta_mcp import audit as audit_module
from src.meta_mcp.audit import AuditEvent, AuditLogger


def test_audit_log_rotation_and_cleanup(tmp_path, monkeypatch):
    """Ensure audit logs rotate by size and cleanup respects retention days."""
    log_file = tmp_path / "audit.jsonl"
    rotation_bytes = 50
    retention_days = 1

    monkeypatch.setattr(audit_module, "AUDIT_ROTATION_BYTES", rotation_bytes)
    monkeypatch.setattr(audit_module, "AUDIT_RETENTION_DAYS", retention_days)

    logger = AuditLogger(str(log_file))

    # Seed log file with data to trigger rotation on next write.
    log_file.write_text("x" * (rotation_bytes + 1))
    logger.log(
        AuditEvent.TOOL_INVOKED,
        tool_name="write_file",
        arguments={"path": "/tmp/example.txt"},
        session_id="session-rotate",
    )

    rotated_files = list(tmp_path.glob("audit.jsonl.*"))
    assert rotated_files, "Expected rotated audit log file to be created."
    assert log_file.exists(), "Expected new audit log file after rotation."

    # Create an old rotated file for cleanup
    old_file = tmp_path / "audit.jsonl.20000101000000"
    old_file.write_text("old log")
    old_mtime = datetime.now(timezone.utc) - timedelta(days=retention_days + 1)
    old_timestamp = old_mtime.timestamp()
    old_file.utime((old_timestamp, old_timestamp))

    logger._cleanup_old_logs()
    assert not old_file.exists(), "Expected old audit log file to be cleaned up."
