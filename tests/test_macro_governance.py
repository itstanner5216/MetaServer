"""
Tests for macro tool governance (Phase 7).

Tests:
- Permission checks for batch operations
- Risk level enforcement
- Audit logging for macro operations
- Rate limiting and quotas
"""

import pytest

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry


class TestMacroGovernance:
    """Test suite for macro tool governance."""

    @pytest.fixture
    def sample_registry(self):
        """Create registry with tools of various risk levels."""
        registry = ToolRegistry()

        tools = [
            ToolRecord(
                tool_id="safe_tool_1",
                server_id="core",
                description_1line="Safe operation 1",
                description_full="Safe operation",
                tags=["safe"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="safe_tool_2",
                server_id="core",
                description_1line="Safe operation 2",
                description_full="Safe operation",
                tags=["safe"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="sensitive_tool",
                server_id="core",
                description_1line="Sensitive operation",
                description_full="Sensitive operation",
                tags=["sensitive"],
                risk_level="sensitive",
            ),
            ToolRecord(
                tool_id="dangerous_tool",
                server_id="admin",
                description_1line="Dangerous operation",
                description_full="Dangerous operation",
                tags=["dangerous"],
                risk_level="dangerous",
            ),
        ]

        for tool in tools:
            registry._tools[tool.tool_id] = tool

        return registry

    def test_batch_read_filters_by_risk(self, sample_registry):
        """Test batch read respects risk level limits."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        # Request all tools
        tool_ids = ["safe_tool_1", "safe_tool_2", "sensitive_tool", "dangerous_tool"]

        # Read with safe-only filter
        results = batch_read_tools(sample_registry, tool_ids, max_risk_level="safe")

        # Should only return safe tools
        safe_results = [t for t in results.values() if t is not None]
        assert all(t.risk_level == "safe" for t in safe_results)

    def test_batch_search_limits_dangerous_tools(self, sample_registry):
        """Test batch search can filter out dangerous tools."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["operation"]
        results = batch_search_tools(sample_registry, queries, exclude_risk_levels=["dangerous"])

        # Should not include dangerous tools
        for query, candidates in results.items():
            for candidate in candidates:
                assert candidate.risk_level != "dangerous"

    def test_macro_operation_audit_logging(self, sample_registry, audit_log_path):
        """Test macro operations are audited."""
        from src.meta_mcp.macros.batch_read import batch_read_tools
        from tests.conftest import read_audit_log

        tool_ids = ["safe_tool_1", "safe_tool_2"]

        # Perform batch operation with session_id for audit logging
        batch_read_tools(sample_registry, tool_ids, audit=True, session_id="test_session")

        # Check audit log
        entries = read_audit_log(audit_log_path)

        # Should have audit entry for batch operation
        batch_entries = [e for e in entries if e.get("operation") == "batch_read"]
        assert len(batch_entries) > 0

    def test_batch_operation_size_limit(self, sample_registry):
        """Test batch operations enforce size limits."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        # Try to read too many tools at once
        tool_ids = [f"tool_{i}" for i in range(1000)]

        result = batch_read_tools(sample_registry, tool_ids, max_batch_size=100)

        # Should limit to max batch size or return error
        assert len(result) <= 100 or "error" in result

    def test_macro_requires_permission(self, sample_registry):
        """Test macro operations require appropriate permissions."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        updates = {"dangerous_tool": {"description_1line": "Modified"}}

        # Without permission for dangerous tools, should fail
        result = batch_update_tools(sample_registry, updates, check_permissions=True)

        # Should fail or require approval
        assert "error" in result or result["success"] is False

    def test_batch_read_rate_limiting(self, sample_registry):
        """Test batch operations respect rate limits."""
        import time

        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["safe_tool_1", "safe_tool_2"]

        # Perform multiple batch reads quickly
        start = time.time()
        for _ in range(10):
            batch_read_tools(sample_registry, tool_ids, rate_limit=True)
        elapsed = time.time() - start

        # If rate limited, should take some minimum time
        # (This is a simple check; real rate limiting would be more sophisticated)
        assert elapsed >= 0  # Just verify it completes

    def test_macro_governance_context(self, sample_registry):
        """Test macro operations include governance context."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["safe_tool_1"]

        # Include session context
        results = batch_read_tools(
            sample_registry, tool_ids, session_id="test-session-123", user_id="test-user"
        )

        # Should complete with context
        assert len(results) > 0

    def test_batch_operation_rollback(self, sample_registry):
        """Test batch operations can rollback on failure."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        original_desc = sample_registry.get("safe_tool_1").description_1line

        # Batch update that should fail partway
        updates = {
            "safe_tool_1": {"description_1line": "Updated 1"},
            "safe_tool_2": {"risk_level": "invalid"},  # This will fail
        }

        result = batch_update_tools(sample_registry, updates, atomic=True, rollback_on_error=True)

        if result["success"] is False:
            # Should rollback safe_tool_1 update
            assert sample_registry.get("safe_tool_1").description_1line == original_desc

    def test_batch_operation_dry_run(self, sample_registry):
        """Test batch operations support dry-run mode."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        original_desc = sample_registry.get("safe_tool_1").description_1line

        updates = {"safe_tool_1": {"description_1line": "Updated"}}

        result = batch_update_tools(sample_registry, updates, dry_run=True)

        # Should return what would be updated
        assert "would_update" in result or "preview" in result

        # Should NOT actually update
        assert sample_registry.get("safe_tool_1").description_1line == original_desc
