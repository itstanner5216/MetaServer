"""
Tests for batch write operations (Phase 7).

Tests:
- Batch updates to registry
- Atomic batch operations
- Error handling
- Validation of batch updates
"""

import pytest

from tests.test_utils import create_test_registry, create_test_tool


class TestBatchWrite:
    """Test suite for batch write operations."""

    @pytest.fixture
    def sample_registry(self):
        """Create registry with sample tools."""
        tools = [
            create_test_tool(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read text and binary files",
                tags=["file", "read"],
                risk_level="safe",
            ),
            create_test_tool(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files to disk",
                description_full="Write text and binary files",
                tags=["file", "write"],
                risk_level="sensitive",
            ),
        ]

        return create_test_registry(tools)

    def test_batch_write_update_tools(self, sample_registry):
        """Test batch update of existing tools."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        updates = {
            "read_file": {"description_1line": "Read files from storage"},
            "write_file": {"description_1line": "Write files to storage"},
        }

        result = batch_update_tools(sample_registry, updates)

        assert result["success"] is True
        assert result["updated"] == 2
        assert sample_registry.get("read_file").description_1line == "Read files from storage"
        assert sample_registry.get("write_file").description_1line == "Write files to storage"

    def test_batch_write_partial_update(self, sample_registry):
        """Test batch update with some invalid tool IDs."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        updates = {
            "read_file": {"description_1line": "Updated description"},
            "nonexistent": {"description_1line": "This should fail"},
        }

        result = batch_update_tools(sample_registry, updates)

        assert result["updated"] == 1
        assert "nonexistent" in result.get("errors", {})

    def test_batch_write_empty_updates(self, sample_registry):
        """Test batch write with empty updates."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        result = batch_update_tools(sample_registry, {})

        assert result["success"] is True
        assert result["updated"] == 0

    def test_batch_write_validation(self, sample_registry):
        """Test batch write validates updates."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        # Try to set invalid risk level
        updates = {"read_file": {"risk_level": "invalid_level"}}

        result = batch_update_tools(sample_registry, updates)

        # Should fail validation
        assert result["success"] is False or "errors" in result

    def test_batch_write_preserves_other_fields(self, sample_registry):
        """Test batch write preserves fields not being updated."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        original_tags = sample_registry.get("read_file").tags.copy()

        updates = {"read_file": {"description_1line": "New description"}}

        batch_update_tools(sample_registry, updates)

        # Tags should be unchanged
        assert sample_registry.get("read_file").tags == original_tags

    def test_batch_write_atomic_operation(self, sample_registry):
        """Test batch write is atomic (all or nothing)."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        original_read_desc = sample_registry.get("read_file").description_1line

        # Mix of valid and invalid updates
        updates = {
            "read_file": {"description_1line": "Updated"},
            "write_file": {"risk_level": "invalid"},  # This should fail
        }

        result = batch_update_tools(sample_registry, updates, atomic=True)

        if result["success"] is False:
            # If atomic and one fails, none should be updated
            assert sample_registry.get("read_file").description_1line == original_read_desc

    def test_batch_write_returns_details(self, sample_registry):
        """Test batch write returns detailed results."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        updates = {"read_file": {"description_1line": "Updated description"}}

        result = batch_update_tools(sample_registry, updates)

        assert "success" in result
        assert "updated" in result
        assert isinstance(result["updated"], int)


class TestBatchWriteAtomicity:
    """Test atomicity strategy for batch tool updates (rollback_on_error)."""

    def test_all_succeed(self):
        """All updates succeed - all tools updated."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        registry = create_test_registry(
            [
                create_test_tool(tool_id="read_file", risk_level="safe"),
                create_test_tool(tool_id="write_file", risk_level="sensitive"),
            ]
        )

        updates = {
            "read_file": {"description_1line": "Read files from storage"},
            "write_file": {"description_1line": "Write files to storage"},
        }

        result = batch_update_tools(
            registry,
            updates,
            atomic=True,
            rollback_on_error=True,
        )

        assert result["success"] is True
        assert result["updated"] == 2
        assert registry.get("read_file").description_1line == "Read files from storage"
        assert registry.get("write_file").description_1line == "Write files to storage"

    def test_one_fails_all_rollback(self):
        """One update fails - all changes rolled back."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        registry = create_test_registry(
            [
                create_test_tool(tool_id="read_file", risk_level="safe"),
                create_test_tool(tool_id="write_file", risk_level="sensitive"),
            ]
        )

        original_read_desc = registry.get("read_file").description_1line
        original_write_risk = registry.get("write_file").risk_level

        updates = {
            "read_file": {"description_1line": "Updated description"},
            "write_file": {"risk_level": "invalid_level"},
        }

        result = batch_update_tools(
            registry,
            updates,
            atomic=True,
            rollback_on_error=True,
        )

        assert result["success"] is False
        assert result.get("rolled_back") is True
        assert registry.get("read_file").description_1line == original_read_desc
        assert registry.get("write_file").risk_level == original_write_risk

    def test_permission_denied_rollback(self):
        """Permission denied on dangerous tool - no changes applied."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        registry = create_test_registry(
            [
                create_test_tool(tool_id="read_file", risk_level="safe"),
                create_test_tool(tool_id="delete_file", risk_level="dangerous"),
            ]
        )

        updates = {
            "read_file": {"description_1line": "Updated description"},
            "delete_file": {"description_1line": "Should not update"},
        }

        result = batch_update_tools(
            registry,
            updates,
            atomic=True,
            rollback_on_error=True,
            check_permissions=True,
        )

        assert result["success"] is False
        assert "error" in result
        assert registry.get("read_file").description_1line == "Test tool: read_file"
        assert registry.get("delete_file").description_1line == "Test tool: delete_file"

    def test_partial_success_handling(self):
        """Partial success allowed when atomicity is disabled."""
        from src.meta_mcp.macros.batch_write import batch_update_tools

        registry = create_test_registry(
            [
                create_test_tool(tool_id="read_file", risk_level="safe"),
                create_test_tool(tool_id="write_file", risk_level="sensitive"),
            ]
        )

        updates = {
            "read_file": {"description_1line": "Updated description"},
            "write_file": {"risk_level": "invalid_level"},
        }

        result = batch_update_tools(
            registry,
            updates,
            atomic=False,
            rollback_on_error=False,
        )

        assert result["updated"] == 1
        assert result["errors"]
        assert registry.get("read_file").description_1line == "Updated description"
        assert registry.get("write_file").risk_level == "sensitive"
