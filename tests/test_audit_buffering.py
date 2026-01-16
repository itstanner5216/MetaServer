from src.meta_mcp.audit import AuditEvent, AuditLogger


def test_audit_buffer_flushes_on_size(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit_logger = AuditLogger(
        log_path=str(log_path),
        buffer_size=2,
        flush_interval=60.0,
    )

    audit_logger.log(
        AuditEvent.MODE_CHANGED,
        old_mode="permission",
        new_mode="read_only",
        changed_by="tester",
    )
    assert len(audit_logger._buffer) == 1

    audit_logger.log(
        AuditEvent.MODE_CHANGED,
        old_mode="read_only",
        new_mode="permission",
        changed_by="tester",
    )
    assert len(audit_logger._buffer) == 0

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
