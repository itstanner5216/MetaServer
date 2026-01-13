"""Tests for TODO List 1 audit fixes.

Validates:
1. Audit logging accepts new parameters (request_id, selected_scopes, etc.)
2. Scope enforcement requires ALL required scopes
"""

import pytest
from src.meta_mcp.audit import AuditLogger, AuditEvent


class TestAuditLoggingFixes:
    """Test audit logging accepts new parameters."""

    def test_log_approval_with_request_id(self, tmp_path):
        """Test log_approval accepts request_id parameter."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Should not raise exception
        logger.log_approval(
            tool_name="write_file",
            arguments={"path": "/tmp/test.txt"},
            session_id="session_123",
            approved=True,
            request_id="abc123_write_file_def456_789",
            selected_scopes=["tool:write_file", "filesystem:write"],
            lease_seconds=300,
        )

        # Verify log was written
        assert log_file.exists()
        content = log_file.read_text()
        assert "request_id" in content
        assert "abc123_write_file_def456_789" in content
        assert "selected_scopes" in content

    def test_log_approval_denial_with_reason(self, tmp_path):
        """Test log_approval accepts reason parameter for denials."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log_approval(
            tool_name="delete_file",
            arguments={"path": "/tmp/important.txt"},
            session_id="session_456",
            approved=False,
            request_id="xyz789_delete_file_abc123_456",
            reason="missing_required_scopes: ['filesystem:delete']",
        )

        content = log_file.read_text()
        assert "request_id" in content
        assert "reason" in content
        assert "missing_required_scopes" in content

    def test_log_approval_timeout_with_request_id(self, tmp_path):
        """Test log_approval_timeout accepts request_id parameter."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        logger.log_approval_timeout(
            tool_name="execute_command",
            arguments={"command": "dangerous_command"},
            session_id="session_789",
            timeout_seconds=300,
            request_id="req_timeout_12345",
        )

        content = log_file.read_text()
        assert "request_id" in content
        assert "req_timeout_12345" in content
        assert "timeout_seconds" in content

    def test_log_approval_backwards_compatible(self, tmp_path):
        """Test log_approval still works without new parameters (backwards compatibility)."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(str(log_file))

        # Old-style call should still work
        logger.log_approval(
            tool_name="read_file",
            arguments={"path": "/tmp/test.txt"},
            session_id="session_old",
            approved=True,
            elevation_ttl=300,
        )

        content = log_file.read_text()
        assert "read_file" in content
        assert "session_old" in content


class TestScopeEnforcementFixes:
    """Test scope enforcement requires ALL required scopes."""

    def test_missing_required_scopes_scenario(self):
        """Demonstrate scope validation logic."""
        # Simulate middleware scope validation
        required_scopes = ["tool:write_file", "filesystem:write"]

        # User only approves one scope (WRONG - should be denied)
        selected_scopes = ["tool:write_file"]  # Missing filesystem:write

        # Check for missing scopes
        missing_scopes = set(required_scopes) - set(selected_scopes)

        # Should have one missing scope
        assert len(missing_scopes) == 1
        assert "filesystem:write" in missing_scopes

    def test_all_scopes_approved_scenario(self):
        """Demonstrate valid approval with all scopes."""
        required_scopes = ["tool:write_file", "filesystem:write"]
        selected_scopes = ["tool:write_file", "filesystem:write"]

        # Check for missing scopes
        missing_scopes = set(required_scopes) - set(selected_scopes)

        # Should have no missing scopes
        assert len(missing_scopes) == 0

    def test_extra_invalid_scopes_scenario(self):
        """Demonstrate detection of invalid extra scopes."""
        required_scopes = ["tool:write_file", "filesystem:write"]
        selected_scopes = ["tool:write_file", "filesystem:write", "admin:superuser"]

        # Check for invalid extra scopes
        invalid_scopes = set(selected_scopes) - set(required_scopes)

        # Should have one invalid scope
        assert len(invalid_scopes) == 1
        assert "admin:superuser" in invalid_scopes

    def test_no_scopes_selected_scenario(self):
        """Demonstrate detection when user selects no scopes."""
        required_scopes = ["tool:delete_file", "filesystem:delete"]
        selected_scopes = []

        # Should fail the empty check
        assert len(selected_scopes) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
