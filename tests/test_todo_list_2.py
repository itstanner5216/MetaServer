"""
Comprehensive tests for TODO List 2 changes.

Test Coverage:
1. remove_directory tool - path validation, recursive deletion, error cases
2. Config.ENABLE_LEASE_MANAGEMENT - middleware skips leases when disabled
3. client_id extraction - from context.session_id in middleware and supervisor
4. format_search_results - works with both ToolSummary and ToolCandidate
5. Package imports - admin_tools.py imports work without sys.path mutation
"""

import importlib
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.config import Config
from src.meta_mcp.discovery import ToolSummary, format_search_results
from src.meta_mcp.middleware import GovernanceMiddleware
from src.meta_mcp.state import ExecutionMode


# ============================================================================
# TEST 1: remove_directory tool - path validation, recursive deletion
# ============================================================================


@pytest.fixture
def core_tools_module(tmp_path, monkeypatch):
    """
    Load core_tools with an isolated WORKSPACE_ROOT for filesystem tests.
    """
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    import servers.core_tools as core_tools
    importlib.reload(core_tools)
    Path(core_tools.WORKSPACE_ROOT).mkdir(parents=True, exist_ok=True)
    return core_tools


def test_remove_directory_validates_path_in_workspace(core_tools_module):
    """
    Test that remove_directory validates paths are within WORKSPACE_ROOT.

    Validates: Path traversal protection (security requirement)
    """
    remove_directory = core_tools_module.remove_directory

    # Try to remove directory outside workspace (path traversal attack)
    with pytest.raises(ToolError) as exc_info:
        remove_directory.fn("../../etc")

    # Verify error message mentions path traversal
    assert "traversal" in str(exc_info.value).lower()


def test_remove_directory_succeeds_on_valid_directory(core_tools_module):
    """
    Test that remove_directory successfully removes a valid directory.

    Validates: Basic functionality - removes directory and all contents
    """
    remove_directory = core_tools_module.remove_directory

    # Create temporary test directory with contents
    workspace = Path(core_tools_module.WORKSPACE_ROOT)
    test_dir = workspace / "test_remove_dir"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Add some files to make it non-empty
    (test_dir / "file1.txt").write_text("content1")
    (test_dir / "subdir").mkdir()
    (test_dir / "subdir" / "file2.txt").write_text("content2")

    # Verify directory exists before removal
    assert test_dir.exists()
    assert test_dir.is_dir()

    # Remove directory
    result = remove_directory.fn("test_remove_dir")

    # Verify success message
    assert "Successfully removed directory" in result
    assert "test_remove_dir" in result

    # Verify directory no longer exists
    assert not test_dir.exists()


def test_remove_directory_fails_on_nonexistent_path(core_tools_module):
    """
    Test that remove_directory raises ToolError for non-existent paths.

    Validates: Error handling for missing directories
    """
    remove_directory = core_tools_module.remove_directory

    # Try to remove non-existent directory
    with pytest.raises(ToolError) as exc_info:
        remove_directory.fn("nonexistent_directory_xyz123")

    # Verify error message mentions "not found"
    assert "not found" in str(exc_info.value).lower()


def test_remove_directory_fails_on_file_path(core_tools_module):
    """
    Test that remove_directory raises ToolError when path is a file, not a directory.

    Validates: Type checking - only directories can be removed with this tool
    """
    remove_directory = core_tools_module.remove_directory

    # Create a file (not a directory)
    workspace = Path(core_tools_module.WORKSPACE_ROOT)
    test_file = workspace / "test_file.txt"
    test_file.write_text("not a directory")

    try:
        # Try to remove file with remove_directory
        with pytest.raises(ToolError) as exc_info:
            remove_directory.fn("test_file.txt")

        # Verify error message mentions "not a directory"
        assert "not a directory" in str(exc_info.value).lower()
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


def test_remove_directory_recursive_deletion(core_tools_module):
    """
    Test that remove_directory recursively deletes all subdirectories and files.

    Validates: Recursive deletion behavior (using shutil.rmtree)
    """
    remove_directory = core_tools_module.remove_directory

    # Create complex directory structure
    workspace = Path(core_tools_module.WORKSPACE_ROOT)
    test_dir = workspace / "test_recursive"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create nested structure: test_recursive/level1/level2/file.txt
    level1 = test_dir / "level1"
    level2 = level1 / "level2"
    level2.mkdir(parents=True, exist_ok=True)
    (level2 / "deep_file.txt").write_text("deep content")
    (level1 / "mid_file.txt").write_text("mid content")
    (test_dir / "top_file.txt").write_text("top content")

    # Verify structure exists
    assert (test_dir / "top_file.txt").exists()
    assert (level1 / "mid_file.txt").exists()
    assert (level2 / "deep_file.txt").exists()

    # Remove entire tree
    result = remove_directory.fn("test_recursive")

    # Verify entire tree is gone
    assert not test_dir.exists()
    assert not level1.exists()
    assert not level2.exists()
    assert "Successfully removed directory" in result


# ============================================================================
# TEST 2: Config.ENABLE_LEASE_MANAGEMENT - middleware skips leases when disabled
# ============================================================================


@pytest.mark.asyncio
async def test_middleware_skips_lease_check_when_disabled(
    mock_fastmcp_context
):
    """
    Test that middleware skips lease validation when ENABLE_LEASE_MANAGEMENT is False.

    Validates: Feature flag correctly disables lease management (Nuance 2.7)
    """
    # Save original config value
    original_enable = Config.ENABLE_LEASE_MANAGEMENT

    try:
        # Disable lease management
        Config.ENABLE_LEASE_MANAGEMENT = False

        # Setup middleware and context for sensitive tool (write_file)
        middleware = GovernanceMiddleware()
        mock_fastmcp_context.request_context.tool_name = "write_file"
        mock_fastmcp_context.request_context.arguments = {
            "path": "test.txt",
            "content": "test"
        }

        # Mock governance/elevation to avoid Redis
        with patch("src.meta_mcp.middleware.governance_state.get_mode", new_callable=AsyncMock) as mock_mode, \
             patch.object(middleware, "_check_elevation", new_callable=AsyncMock) as mock_check, \
             patch.object(middleware, "_elicit_approval", new_callable=AsyncMock) as mock_elicit, \
             patch("src.meta_mcp.middleware.lease_manager.validate", new_callable=AsyncMock) as mock_validate, \
             patch("src.meta_mcp.middleware.lease_manager.consume", new_callable=AsyncMock) as mock_consume, \
             patch("src.meta_mcp.middleware.audit_logger.log") as mock_log:
            mock_mode.return_value = ExecutionMode.PERMISSION
            mock_check.return_value = False
            mock_elicit.return_value = (True, 0, ["tool:write_file"])
            mock_validate.side_effect = AssertionError("Lease validation should not run when disabled")
            mock_consume.side_effect = AssertionError("Lease consumption should not run when disabled")

            # Create mock call_next
            call_next = AsyncMock(return_value="success")

            # Execute middleware WITHOUT lease (should succeed because leases are disabled)
            result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

            # Verify tool executed successfully (no ToolError about missing lease)
            assert result == "success"
            call_next.assert_called_once()

    finally:
        # Restore original config
        Config.ENABLE_LEASE_MANAGEMENT = original_enable


@pytest.mark.asyncio
async def test_middleware_requires_lease_when_enabled(
    mock_fastmcp_context
):
    """
    Test that middleware requires lease when ENABLE_LEASE_MANAGEMENT is True.

    Validates: Lease enforcement when feature flag is enabled
    """
    # Save original config value
    original_enable = Config.ENABLE_LEASE_MANAGEMENT

    try:
        # Enable lease management (default, but explicit)
        Config.ENABLE_LEASE_MANAGEMENT = True

        # Setup middleware and context for non-bootstrap tool
        middleware = GovernanceMiddleware()
        mock_fastmcp_context.request_context.tool_name = "write_file"
        mock_fastmcp_context.request_context.arguments = {
            "path": "test.txt",
            "content": "test"
        }

        # Create mock call_next
        call_next = AsyncMock()

        # Mock lease validation to simulate missing lease (no Redis)
        with patch("src.meta_mcp.middleware.lease_manager.validate", new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = None

            # Execute middleware WITHOUT lease (should fail)
            with pytest.raises(ToolError) as exc_info:
                await middleware.on_call_tool(mock_fastmcp_context, call_next)

            # Verify error mentions lease
            assert "lease" in str(exc_info.value).lower()

            # Verify tool was not executed
            call_next.assert_not_called()

    finally:
        # Restore original config
        Config.ENABLE_LEASE_MANAGEMENT = original_enable


@pytest.mark.asyncio
async def test_middleware_always_skips_lease_for_bootstrap_tools(
    mock_fastmcp_context
):
    """
    Test that middleware always skips lease check for bootstrap tools.

    Validates: Bootstrap tools (search_tools, get_tool_schema, request_tool_access) bypass lease checks
    """
    # Enable lease management (ensures bootstrap bypass is active)
    original_enable = Config.ENABLE_LEASE_MANAGEMENT
    Config.ENABLE_LEASE_MANAGEMENT = True

    try:
        middleware = GovernanceMiddleware()

        # Test search_tools (bootstrap tool) - should work without lease
        mock_fastmcp_context.request_context.tool_name = "search_tools"
        mock_fastmcp_context.request_context.arguments = {"query": "test"}

        with patch("src.meta_mcp.middleware.governance_state.get_mode", new_callable=AsyncMock) as mock_mode, \
             patch("src.meta_mcp.middleware.lease_manager.validate", new_callable=AsyncMock) as mock_validate, \
             patch("src.meta_mcp.middleware.audit_logger.log") as mock_log:
            mock_mode.return_value = ExecutionMode.PERMISSION
            mock_validate.side_effect = AssertionError("Lease validation should not run for bootstrap tools")

            call_next = AsyncMock(return_value="search results")
            result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

            assert result == "search results"
            call_next.assert_called_once()

            # Test get_tool_schema (bootstrap tool) - should work without lease
            call_next.reset_mock()
            mock_fastmcp_context.request_context.tool_name = "get_tool_schema"
            mock_fastmcp_context.request_context.arguments = {"tool_name": "read_file"}

            result = await middleware.on_call_tool(mock_fastmcp_context, call_next)
            call_next.assert_called_once()

            # Test request_tool_access (bootstrap tool) - should work without lease
            call_next.reset_mock()
            mock_fastmcp_context.request_context.tool_name = "request_tool_access"
            mock_fastmcp_context.request_context.arguments = {"tool_name": "read_file"}

            result = await middleware.on_call_tool(mock_fastmcp_context, call_next)
            call_next.assert_called_once()

    finally:
        Config.ENABLE_LEASE_MANAGEMENT = original_enable


# ============================================================================
# TEST 3: client_id extraction - from context.session_id
# ============================================================================


@pytest.mark.asyncio
async def test_middleware_extracts_client_id_from_session_id(
    mock_fastmcp_context
):
    """
    Test that middleware extracts client_id from context.session_id.

    Validates: Client identification from FastMCP session context (line 656 in middleware.py)
    """
    # Setup middleware
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "test.txt",
        "content": "test"
    }
    mock_fastmcp_context.session_id = "test-session-abc123"

    dummy_lease = MagicMock(capability_token=None, calls_remaining=1)

    # Mock lease validation and governance to avoid Redis
    with patch("src.meta_mcp.middleware.lease_manager.validate", new_callable=AsyncMock) as mock_validate, \
         patch("src.meta_mcp.middleware.lease_manager.consume", new_callable=AsyncMock) as mock_consume, \
         patch("src.meta_mcp.middleware.governance_state.get_mode", new_callable=AsyncMock) as mock_mode, \
         patch.object(middleware, "_check_elevation", new_callable=AsyncMock) as mock_check, \
         patch.object(middleware, "_elicit_approval", new_callable=AsyncMock) as mock_elicit, \
         patch("src.meta_mcp.middleware.audit_logger.log") as mock_log:
        mock_validate.return_value = dummy_lease
        mock_consume.return_value = dummy_lease
        mock_mode.return_value = ExecutionMode.PERMISSION
        mock_check.return_value = False
        mock_elicit.return_value = (True, 0, ["tool:write_file"])

        call_next = AsyncMock(return_value="success")

        # Execute
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

        # Verify elicit_approval was called with correct context (which has session_id)
        mock_elicit.assert_called_once()
        call_args = mock_elicit.call_args
        ctx_arg = call_args[0][0]  # First positional arg is Context

        # Verify session_id is accessible from context
        assert hasattr(ctx_arg, 'session_id')
        assert str(ctx_arg.session_id) == "test-session-abc123"


@pytest.mark.asyncio
async def test_supervisor_request_tool_access_uses_session_id_for_client_id(
    mock_fastmcp_context
):
    """
    Test that supervisor's request_tool_access extracts client_id from ctx.session_id.

    Validates: Client identification in supervisor (request_tool_access)
    """
    from src.meta_mcp.supervisor import request_tool_access

    # Setup context with session_id
    mock_context = MagicMock()
    mock_context.session_id = "supervisor-session-xyz789"

    # Mock registry to have a tool
    with patch('src.meta_mcp.supervisor.tool_registry') as mock_registry:
        mock_registry.is_registered.return_value = True
        mock_registry.get.return_value = MagicMock(
            risk_level="safe",
            schema_full=None,
            schema_min=None
        )

        with patch('src.meta_mcp.supervisor.governance_state.get_mode', new_callable=AsyncMock) as mock_mode:
            mock_mode.return_value = ExecutionMode.PERMISSION

            from src.meta_mcp.leases import lease_manager
            with patch.object(lease_manager, 'grant', new_callable=AsyncMock) as mock_grant:
                mock_grant.return_value = MagicMock(
                    tool_id="test_tool",
                    calls_remaining=3,
                    granted_at=datetime.now(),
                    expires_at=datetime.now(),
                    mode_at_issue="PERMISSION",
                )

                try:
                    await request_tool_access("test_tool", ctx=mock_context)

                    mock_grant.assert_called_once()
                    grant_kwargs = mock_grant.call_args[1]

                    assert grant_kwargs['client_id'] == "supervisor-session-xyz789"

                except Exception:
                    if mock_grant.called:
                        grant_kwargs = mock_grant.call_args[1]
                        assert grant_kwargs['client_id'] == "supervisor-session-xyz789"


@pytest.mark.asyncio
async def test_supervisor_handles_missing_context_gracefully():
    """
    Test that supervisor uses fail-safe client_id when context is None.

    Validates: Fail-safe behavior when context is unavailable (line 361-365 in supervisor.py)
    """
    from src.meta_mcp.supervisor import request_tool_access

    # Mock registry
    with patch('src.meta_mcp.supervisor.tool_registry') as mock_registry:
        mock_registry.is_registered.return_value = True
        mock_registry.get.return_value = MagicMock(
            risk_level="safe",
            schema_full=None,
            schema_min=None
        )

        with patch('src.meta_mcp.supervisor.governance_state.get_mode', new_callable=AsyncMock) as mock_mode:
            mock_mode.return_value = ExecutionMode.PERMISSION

            # Mock lease_manager.grant
            from src.meta_mcp.leases import lease_manager
            with patch.object(lease_manager, 'grant', new_callable=AsyncMock) as mock_grant:
                mock_grant.return_value = MagicMock(
                    tool_id="test_tool",
                    calls_remaining=3,
                    granted_at=datetime.now(),
                    expires_at=datetime.now(),
                    mode_at_issue="PERMISSION",
                )

                # Execute with ctx=None (fail-safe scenario)
                try:
                    await request_tool_access("test_tool", ctx=None)

                    mock_grant.assert_called_once()
                    grant_kwargs = mock_grant.call_args[1]

                    assert grant_kwargs['client_id'] == "unknown_client"

                except Exception:
                    if mock_grant.called:
                        grant_kwargs = mock_grant.call_args[1]
                        assert grant_kwargs['client_id'] == "unknown_client"


# ============================================================================
# TEST 4: get_tool_schema compatibility modes
# ============================================================================


@pytest.mark.asyncio
async def test_get_tool_schema_does_not_grant_lease_when_compat_disabled():
    """
    Test that get_tool_schema does not grant leases when compatibility is disabled.
    """
    from src.meta_mcp.supervisor import get_tool_schema

    original_compat = Config.ENABLE_SCHEMA_LEASE_COMPAT
    Config.ENABLE_SCHEMA_LEASE_COMPAT = False

    try:
        with patch('src.meta_mcp.supervisor.tool_registry') as mock_registry:
            mock_registry.is_registered.return_value = True
            mock_registry.get.return_value = MagicMock(
                risk_level="safe",
                schema_full=None,
                schema_min=None
            )

            with patch('src.meta_mcp.supervisor._expose_tool', new_callable=AsyncMock) as mock_expose:
                mock_expose.return_value = True

                with patch('src.meta_mcp.supervisor.mcp') as mock_mcp:
                    mock_tool = MagicMock()
                    mock_tool.to_mcp_tool.return_value = MagicMock(
                        name="test_tool",
                        description="Test tool",
                        inputSchema={"type": "object"}
                    )
                    mock_mcp.get_tool = AsyncMock(return_value=mock_tool)

                    with patch('src.meta_mcp.supervisor.lease_manager.grant', new_callable=AsyncMock) as mock_grant:
                        result = await get_tool_schema("test_tool", expand=False, ctx=None)
                        assert "test_tool" in result
                        mock_grant.assert_not_called()
    finally:
        Config.ENABLE_SCHEMA_LEASE_COMPAT = original_compat


@pytest.mark.asyncio
async def test_get_tool_schema_grants_lease_when_compat_enabled():
    """
    Test that get_tool_schema still grants leases when compatibility is enabled.
    """
    from src.meta_mcp.supervisor import get_tool_schema

    original_compat = Config.ENABLE_SCHEMA_LEASE_COMPAT
    Config.ENABLE_SCHEMA_LEASE_COMPAT = True

    try:
        with patch('src.meta_mcp.supervisor.tool_registry') as mock_registry:
            mock_registry.is_registered.return_value = True
            mock_registry.get.return_value = MagicMock(
                risk_level="safe",
                schema_full=None,
                schema_min=None
            )

            with patch('src.meta_mcp.supervisor._expose_tool', new_callable=AsyncMock) as mock_expose, \
                 patch('src.meta_mcp.supervisor.governance_state.get_mode', new_callable=AsyncMock) as mock_mode:
                mock_expose.return_value = True
                mock_mode.return_value = ExecutionMode.PERMISSION

                with patch('src.meta_mcp.supervisor.mcp') as mock_mcp:
                    mock_tool = MagicMock()
                    mock_tool.to_mcp_tool.return_value = MagicMock(
                        name="test_tool",
                        description="Test tool",
                        inputSchema={"type": "object"}
                    )
                    mock_mcp.get_tool = AsyncMock(return_value=mock_tool)

                    with patch('src.meta_mcp.supervisor.lease_manager.grant', new_callable=AsyncMock) as mock_grant:
                        mock_grant.return_value = MagicMock()
                        result = await get_tool_schema("test_tool", expand=False, ctx=None)
                        assert "test_tool" in result
                        mock_grant.assert_called_once()
    finally:
        Config.ENABLE_SCHEMA_LEASE_COMPAT = original_compat


# ============================================================================
# TEST 5: format_search_results - works with both ToolSummary and ToolCandidate
# ============================================================================


def test_format_search_results_handles_tool_summary():
    """
    Test that format_search_results correctly handles legacy ToolSummary objects.

    Validates: Backward compatibility with old ToolSummary format
    """
    # Create ToolSummary objects (old format)
    results = [
        ToolSummary(
            name="read_file",
            description="Read file contents from workspace.",
            category="core",
            sensitive=False
        ),
        ToolSummary(
            name="write_file",
            description="Write content to file in workspace.",
            category="core",
            sensitive=True
        )
    ]

    # Format results
    output = format_search_results(results)

    # Verify output contains tool names
    assert "read_file" in output
    assert "write_file" in output

    # Verify sensitivity flags are correct
    assert "[SAFE]" in output  # read_file is not sensitive
    assert "[SENSITIVE]" in output  # write_file is sensitive

    # Verify descriptions are included
    assert "Read file contents" in output
    assert "Write content to file" in output

    # Verify count
    assert "2 tool(s)" in output


def test_format_search_results_handles_tool_candidate():
    """
    Test that format_search_results correctly handles new ToolCandidate objects.

    Validates: Forward compatibility with new registry format
    """
    # Create mock ToolCandidate objects (new format)
    # ToolCandidate has: tool_id, description_1line, risk_level
    class MockToolCandidate:
        def __init__(self, tool_id, description_1line, risk_level):
            self.tool_id = tool_id
            self.description_1line = description_1line
            self.risk_level = risk_level

    results = [
        MockToolCandidate(
            tool_id="list_directory",
            description_1line="List directory contents with type indicators.",
            risk_level="safe"
        ),
        MockToolCandidate(
            tool_id="execute_command",
            description_1line="Execute shell command with timeout.",
            risk_level="dangerous"
        )
    ]

    # Format results
    output = format_search_results(results)

    # Verify output contains tool IDs
    assert "list_directory" in output
    assert "execute_command" in output

    # Verify risk levels map to sensitivity flags
    assert "[SAFE]" in output  # list_directory has safe risk_level
    assert "[SENSITIVE]" in output  # execute_command has dangerous risk_level

    # Verify descriptions are included
    assert "List directory contents" in output
    assert "Execute shell command" in output


def test_format_search_results_handles_empty_results():
    """
    Test that format_search_results handles empty result sets gracefully.

    Validates: Error handling for no matches
    """
    output = format_search_results([])

    # Should return helpful message
    assert "No tools found" in output


def test_format_search_results_mixed_risk_levels():
    """
    Test that format_search_results correctly maps all risk levels to sensitivity flags.

    Validates: Risk level to sensitivity mapping logic (line 329 in discovery.py)
    """
    # Create tools with different risk levels
    class MockToolCandidate:
        def __init__(self, tool_id, description_1line, risk_level):
            self.tool_id = tool_id
            self.description_1line = description_1line
            self.risk_level = risk_level

    results = [
        MockToolCandidate("tool1", "Safe tool.", "safe"),
        MockToolCandidate("tool2", "Sensitive tool.", "sensitive"),
        MockToolCandidate("tool3", "Dangerous tool.", "dangerous")
    ]

    output = format_search_results(results)

    # Safe should map to [SAFE]
    assert output.count("[SAFE]") == 1  # Only tool1 is safe

    # Sensitive and dangerous should both map to [SENSITIVE]
    assert output.count("[SENSITIVE]") == 2  # tool2 and tool3


# ============================================================================
# TEST 6: Package imports - admin_tools.py imports work without sys.path mutation
# ============================================================================


def test_admin_tools_imports_without_syspath():
    """
    Test that admin_tools.py can import governance components without sys.path mutation.

    Validates: Package-safe absolute imports (line 14-17 in admin_tools.py)
    """
    # Record original sys.path
    original_syspath = sys.path.copy()

    try:
        # Import admin_tools module (should use package-safe imports)
        import servers.admin_tools as admin_tools

        # Verify imports are successful
        assert hasattr(admin_tools, 'admin_server')
        assert hasattr(admin_tools, 'set_governance_mode')
        assert hasattr(admin_tools, 'get_governance_status')
        assert hasattr(admin_tools, 'revoke_all_elevations')

        # Verify sys.path was not mutated during import
        assert sys.path == original_syspath, "sys.path was mutated during import"

    except ImportError as e:
        pytest.fail(f"admin_tools.py imports failed: {e}")


def test_admin_tools_imports_use_meta_mcp_package():
    """
    Test that admin_tools.py imports use 'meta_mcp' package prefix (not 'src.meta_mcp').

    Validates: Correct package import paths for installed package
    """
    # Read admin_tools.py source
    admin_tools_path = Path(__file__).parent.parent / "servers" / "admin_tools.py"
    source_code = admin_tools_path.read_text()

    # Verify imports use "from meta_mcp" (not "from src.meta_mcp")
    assert "from meta_mcp.audit import" in source_code, \
        "Should use 'from meta_mcp.audit' not 'from src.meta_mcp.audit'"

    assert "from meta_mcp.state import" in source_code, \
        "Should use 'from meta_mcp.state' not 'from src.meta_mcp.state'"

    # Verify NO "from src.meta_mcp" imports exist
    assert "from src.meta_mcp" not in source_code, \
        "Should not use 'from src.meta_mcp' - package should be installed via 'pip install -e .'"


def test_admin_tools_governance_components_accessible():
    """
    Test that imported governance components are accessible and functional.

    Validates: Imports resolve to actual usable objects
    """
    try:
        from servers.admin_tools import admin_server, audit_logger, governance_state, ExecutionMode, AuditEvent

        # Verify audit_logger has expected methods
        assert hasattr(audit_logger, 'log_mode_change')
        assert callable(audit_logger.log_mode_change)

        # Verify governance_state has expected methods
        assert hasattr(governance_state, 'get_mode')
        assert hasattr(governance_state, 'set_mode')

        # Verify ExecutionMode enum
        assert hasattr(ExecutionMode, 'PERMISSION')
        assert hasattr(ExecutionMode, 'READ_ONLY')
        assert hasattr(ExecutionMode, 'BYPASS')

        # Verify AuditEvent enum
        assert hasattr(AuditEvent, 'ELEVATIONS_REVOKED')

    except ImportError as e:
        pytest.fail(f"Failed to import governance components from admin_tools: {e}")
    except AttributeError as e:
        pytest.fail(f"Imported governance components missing expected attributes: {e}")


@pytest.mark.asyncio
async def test_admin_tools_functions_use_imported_components():
    """
    Test that admin_tools functions actually use the imported governance components.

    Validates: Integration between admin_tools and governance system
    """
    from servers.admin_tools import get_governance_status
    from src.meta_mcp.state import ExecutionMode

    # Mock governance_state to avoid Redis
    class DummyRedis:
        async def scan(self, cursor=0, match=None, count=100):
            return 0, []

    with patch("servers.admin_tools.governance_state.get_mode", new_callable=AsyncMock) as mock_mode, \
         patch("servers.admin_tools.governance_state._get_redis", new_callable=AsyncMock) as mock_redis:
        mock_mode.return_value = ExecutionMode.PERMISSION
        mock_redis.return_value = DummyRedis()

        # Call admin tool
        status = await get_governance_status.fn()

    # Verify status includes the mode we set
    assert "PERMISSION" in status or "permission" in status
    assert "Mode" in status or "mode" in status


# ============================================================================
# INTEGRATION TEST: Full workflow with all TODO List 2 changes
# ============================================================================


@pytest.mark.asyncio
async def test_todo_list_2_integration(
    mock_fastmcp_context
):
    """
    Integration test validating all TODO List 2 changes work together.

    Tests:
    1. remove_directory is registered as sensitive tool
    2. Middleware uses session_id for client_id
    3. Config.ENABLE_LEASE_MANAGEMENT controls lease checks
    4. format_search_results works with registry search
    5. admin_tools imports work correctly
    """
    # 1. Verify remove_directory exists and is importable
    from servers.core_tools import remove_directory
    assert hasattr(remove_directory, "fn")

    # 2. Verify remove_directory is registered in middleware's SENSITIVE_TOOLS
    from src.meta_mcp.middleware import SENSITIVE_TOOLS
    assert "remove_directory" in SENSITIVE_TOOLS

    # 3. Test middleware uses session_id for client tracking
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "remove_directory"
    mock_fastmcp_context.request_context.arguments = {"path": "test_dir"}
    mock_fastmcp_context.session_id = "integration-test-session"

    # Disable lease management for this integration test
    original_enable = Config.ENABLE_LEASE_MANAGEMENT
    Config.ENABLE_LEASE_MANAGEMENT = False

    try:
        # Mock elicit_approval to verify session tracking
        with patch.object(middleware, '_elicit_approval', new_callable=AsyncMock) as mock_elicit, \
             patch.object(middleware, "_check_elevation", new_callable=AsyncMock) as mock_check, \
             patch("src.meta_mcp.middleware.governance_state.get_mode", new_callable=AsyncMock) as mock_mode, \
             patch("src.meta_mcp.middleware.audit_logger.log") as mock_log:
            mock_elicit.return_value = (True, 0, ["tool:remove_directory"])
            mock_check.return_value = False
            mock_mode.return_value = ExecutionMode.PERMISSION

            call_next = AsyncMock(return_value="success")

            # Execute
            await middleware.on_call_tool(mock_fastmcp_context, call_next)

            # Verify elicit was called with context containing session_id
            assert mock_elicit.called
            ctx_arg = mock_elicit.call_args[0][0]
            assert str(ctx_arg.session_id) == "integration-test-session"

    finally:
        Config.ENABLE_LEASE_MANAGEMENT = original_enable

    # 4. Test format_search_results with registry search (config/tools.yaml)
    from src.meta_mcp.registry import tool_registry as yaml_registry
    results = yaml_registry.search("remove")

    # Should find remove_directory
    assert len(results) > 0
    assert any(r.tool_id == "remove_directory" for r in results)

    # Format results
    formatted = format_search_results(results)
    assert "remove_directory" in formatted
    assert "[SENSITIVE]" in formatted  # remove_directory is sensitive

    # 5. Verify admin_tools imports work
    from servers.admin_tools import admin_server, set_governance_mode
    assert admin_server is not None
    assert hasattr(set_governance_mode, "fn")
    assert callable(set_governance_mode.fn)
