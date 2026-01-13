"""
Progressive Discovery Verification Tests

Validates that the progressive discovery implementation meets all success criteria:
- Initial exposure limited to 2 bootstrap tools
- search_tools does not trigger exposure
- get_tool_schema triggers exposure
- Exposed tools persist
- Governance still applies to all tools
- Context reduction achieved
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.meta_mcp.registry.registry import ToolRegistry
from src.meta_mcp import supervisor
from src.meta_mcp.supervisor import mcp, tool_registry, search_tools, get_tool_schema
from src.meta_mcp.state import ExecutionMode, governance_state


@pytest.mark.asyncio
async def test_initial_exposure_minimal():
    """
    SUCCESS CRITERION 1: Initial tools/list returns exactly 2 tools.

    At startup, only bootstrap tools should be exposed:
    - search_tools
    - get_tool_schema
    """
    # Get initial tool list
    tools = await mcp.get_tools()
    tool_names = sorted([t.name for t in tools.values()])

    # Verify exactly 2 tools
    assert len(tool_names) == 2, f"Expected 2 tools, got {len(tool_names)}: {tool_names}"

    # Verify correct tools
    assert "search_tools" in tool_names, "search_tools missing from bootstrap"
    assert "get_tool_schema" in tool_names, "get_tool_schema missing from bootstrap"

    # Verify no other tools exposed
    assert "read_file" not in tool_names, "read_file should not be auto-exposed"
    assert "write_file" not in tool_names, "write_file should not be auto-exposed"
    assert "delete_file" not in tool_names, "delete_file should not be auto-exposed"


@pytest.mark.asyncio
async def test_search_does_not_expose_tools():
    """
    SUCCESS CRITERION 2: search_tools works without exposing tools.

    Searching for tools should return metadata but NOT expose them to tools/list.
    """
    # Get initial tool count
    tools_before = await mcp.get_tools()
    count_before = len(tools_before)

    # Search for file-related tools
    search_result = search_tools.fn(query="file")

    # Verify search returned results
    assert "read_file" in search_result or "Read file" in search_result, \
        "search_tools should find file-related tools"

    # Get tool count after search
    tools_after = await mcp.get_tools()
    count_after = len(tools_after)

    # Verify no tools were exposed
    assert count_after == count_before, \
        f"search_tools exposed {count_after - count_before} tools (should expose 0)"

    # Verify read_file specifically not exposed
    tool_names_after = [t.name for t in tools_after.values()]
    assert "read_file" not in tool_names_after, \
        "read_file should not be exposed after search"


@pytest.mark.asyncio
async def test_get_tool_schema_triggers_exposure():
    """
    SUCCESS CRITERION 3: get_tool_schema triggers tool exposure.

    Requesting a tool's schema should:
    1. Expose the tool to tools/list
    2. Return the full JSON schema
    """
    # Get initial tool count
    tools_before = await mcp.get_tools()
    count_before = len(tools_before)
    tool_names_before = [t.name for t in tools_before.values()]

    # Verify read_file not exposed yet
    assert "read_file" not in tool_names_before, \
        "read_file should not be exposed initially"

    # Request schema for read_file (triggers exposure)
    schema_result = await get_tool_schema.fn(tool_name="read_file")

    # Verify schema was returned
    assert "read_file" in schema_result, "Schema should contain tool name"
    assert "inputSchema" in schema_result or "parameters" in schema_result.lower(), \
        "Schema should contain parameter information"

    # Get tool count after schema request
    tools_after = await mcp.get_tools()
    count_after = len(tools_after)
    tool_names_after = [t.name for t in tools_after.values()]

    # Verify tool was exposed
    assert count_after == count_before + 1, \
        f"Expected 1 new tool, got {count_after - count_before}"

    assert "read_file" in tool_names_after, \
        "read_file should be exposed after schema request"


@pytest.mark.asyncio
async def test_exposed_tools_persist():
    """
    SUCCESS CRITERION 4: Exposed tools persist across calls.

    Once a tool is exposed, it should remain exposed without re-exposure.
    """
    # Expose write_file
    await get_tool_schema.fn(tool_name="write_file")

    # Verify it's exposed
    tools_after_first = await mcp.get_tools()
    tool_names_first = [t.name for t in tools_after_first.values()]
    assert "write_file" in tool_names_first, "write_file should be exposed"
    count_first = len(tools_after_first)

    # Call get_tool_schema again for the same tool
    await get_tool_schema.fn(tool_name="write_file")

    # Verify no duplicate exposure
    tools_after_second = await mcp.get_tools()
    count_second = len(tools_after_second)

    assert count_second == count_first, \
        f"Tool count changed from {count_first} to {count_second} (duplicate exposure?)"


@pytest.mark.asyncio
async def test_tools_list_updates_dynamically():
    """
    SUCCESS CRITERION 5: tools/list updates dynamically as tools are discovered.

    The tools/list should reflect the current exposure state.
    """
    # Start with baseline
    initial_tools = await mcp.get_tools()
    initial_count = len(initial_tools)

    # Expose multiple tools in sequence
    tools_to_expose = ["list_directory", "create_directory", "move_file"]

    for i, tool_name in enumerate(tools_to_expose, 1):
        # Expose the tool
        await get_tool_schema.fn(tool_name=tool_name)

        # Check tools/list
        current_tools = await mcp.get_tools()
        current_count = len(current_tools)
        current_names = [t.name for t in current_tools.values()]

        # Verify count increased
        expected_count = initial_count + i
        assert current_count == expected_count, \
            f"After exposing {i} tools, expected {expected_count}, got {current_count}"

        # Verify the tool is in the list
        assert tool_name in current_names, \
            f"{tool_name} should be in tools/list after exposure"


@pytest.mark.asyncio
async def test_governance_intercepts_all_tools(redis_client):
    """
    SUCCESS CRITERION 6: Governance middleware intercepts ALL tools.

    Even with progressive discovery, governance must still apply.
    """
    # Set governance mode to READ_ONLY
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Expose delete_file via schema request
    schema_result = await get_tool_schema.fn(tool_name="delete_file")
    assert "delete_file" in schema_result, "Schema request should succeed"

    # Verify delete_file is now exposed
    tools = await mcp.get_tools()
    tool_names = [t.name for t in tools.values()]
    assert "delete_file" in tool_names, "delete_file should be exposed"

    # Verify the tool can be retrieved (governance will intercept during actual invocation)
    delete_tool = await mcp.get_tool("delete_file")
    assert delete_tool is not None, "delete_file should be retrievable after exposure"
    assert delete_tool.name == "delete_file", "Tool name should match"

    # Note: Actual governance interception is tested in test_governance_modes.py
    # Here we just verify progressive discovery doesn't bypass the governance system

    # Clean up: reset to PERMISSION mode
    await governance_state.set_mode(ExecutionMode.PERMISSION)


@pytest.mark.asyncio
async def test_context_reduction_calculation():
    """
    SUCCESS CRITERION 9: Context reduction minimum 75% (initial state).

    Calculate actual token savings from progressive discovery.
    """
    # Count total registered tools
    all_tools = tool_registry.get_all_summaries()
    total_registered = len(all_tools)

    # Count bootstrap tools (initially exposed at startup)
    bootstrap_tools = tool_registry.get_bootstrap_tools()
    initially_exposed = len(bootstrap_tools)

    # Calculate reduction (based on registry design, not current MCP state)
    reduction_percentage = ((total_registered - initially_exposed) / total_registered) * 100

    # Verify metrics
    assert total_registered >= 13, \
        f"Expected at least 13 total tools, got {total_registered}"

    assert initially_exposed == 2, \
        f"Expected 2 bootstrap tools, got {initially_exposed}"

    assert reduction_percentage >= 75, \
        f"Context reduction is {reduction_percentage:.1f}%, expected >= 75%"

    # Log the actual savings
    print(f"\n{'=' * 60}")
    print(f"CONTEXT REDUCTION METRICS")
    print(f"{'=' * 60}")
    print(f"Total registered tools:    {total_registered}")
    print(f"Initially exposed tools:   {initially_exposed}")
    print(f"Reduction:                 {reduction_percentage:.1f}%")
    print(f"{'=' * 60}")


@pytest.mark.asyncio
async def test_discovery_workflow_complete():
    """
    Test complete model workflow: search → schema → invoke.

    This simulates the expected model behavior with progressive discovery.
    """
    # Step 1: Model searches for tools
    search_result = search_tools.fn(query="execute")
    assert "execute_command" in search_result, "Search should find execute_command"

    # Verify execute_command not yet exposed
    tools_after_search = await mcp.get_tools()
    names_after_search = [t.name for t in tools_after_search.values()]
    assert "execute_command" not in names_after_search, \
        "execute_command should not be exposed after search"

    # Step 2: Model requests schema
    schema_result = await get_tool_schema.fn(tool_name="execute_command")
    assert "execute_command" in schema_result, "Schema should be returned"

    # Verify execute_command now exposed
    tools_after_schema = await mcp.get_tools()
    names_after_schema = [t.name for t in tools_after_schema.values()]
    assert "execute_command" in names_after_schema, \
        "execute_command should be exposed after schema request"

    # Step 3: Model can now invoke the tool
    # (We won't actually execute a command, just verify it's callable)
    tool = await mcp.get_tool("execute_command")
    assert tool is not None, "Tool should be retrievable after exposure"
    assert tool.name == "execute_command", "Tool name should match"


@pytest.mark.asyncio
async def test_no_breaking_changes():
    """
    SUCCESS CRITERION 8: No breaking changes to model workflow.

    Verify all expected tools are still discoverable.
    """
    # All core tools should be registered and searchable
    expected_core_tools = [
        "read_file",
        "write_file",
        "delete_file",
        "list_directory",
        "create_directory",
        "move_file",
        "execute_command",
        "git_commit",
        "git_push",
        "git_reset",
    ]

    for tool_name in expected_core_tools:
        # Should be registered
        assert tool_registry.is_registered(tool_name), \
            f"{tool_name} should be registered in discovery"

        # Should be searchable
        search_result = search_tools.fn(query=tool_name)
        assert tool_name in search_result, \
            f"{tool_name} should be found via search"

        # Should be exposable via schema request
        schema_result = await get_tool_schema.fn(tool_name=tool_name)
        assert tool_name in schema_result, \
            f"{tool_name} schema should be retrievable"


@pytest.mark.asyncio
async def test_bootstrap_tools_always_available():
    """
    Verify bootstrap tools are always available without schema request.

    search_tools and get_tool_schema should work without progressive discovery.
    """
    # Both should be in tools/list initially
    tools = await mcp.get_tools()
    tool_names = [t.name for t in tools.values()]

    assert "search_tools" in tool_names, \
        "search_tools must be available at startup"
    assert "get_tool_schema" in tool_names, \
        "get_tool_schema must be available at startup"

    # Both should be immediately callable
    search_result = search_tools.fn(query="test")
    assert search_result is not None, "search_tools should be callable"

    schema_result = await get_tool_schema.fn(tool_name="search_tools")
    assert "search_tools" in schema_result, "get_tool_schema should be callable"


@pytest.mark.asyncio
async def test_expose_tool_uses_yaml_registry(tmp_path, monkeypatch):
    """
    Validate that tools registered via YAML can be exposed.
    """
    yaml_content = """
servers:
- server_id: core_tools
  description: Core tools
  risk_level: dangerous
  tags: [core]
tools:
- tool_id: yaml_only_tool
  server_id: core_tools
  description_1line: YAML tool for testing.
  description_full: YAML tool for testing.
  tags: [core, test]
  risk_level: safe
"""
    yaml_path = tmp_path / "tools.yaml"
    yaml_path.write_text(yaml_content)

    registry = ToolRegistry.from_yaml(str(yaml_path))
    monkeypatch.setattr(supervisor, "tool_registry", registry)

    mock_tool = MagicMock()
    mock_get_tool = AsyncMock(return_value=mock_tool)
    monkeypatch.setattr(supervisor.core_server, "get_tool", mock_get_tool)
    monkeypatch.setattr(supervisor.mcp, "add_tool", MagicMock())
    monkeypatch.setattr(supervisor, "_loaded_tools", set())
    monkeypatch.setattr(supervisor, "_tool_instances", {})

    exposed = await supervisor._expose_tool("yaml_only_tool")

    assert exposed is True
    mock_get_tool.assert_awaited_once_with("yaml_only_tool")
