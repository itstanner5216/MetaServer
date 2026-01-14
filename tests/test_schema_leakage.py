"""
CRITICAL Security Tests for Schema Leakage Prevention (Phase 4)

These tests ensure that tool schemas are not leaked before authorization.

Schema leakage allows attackers to:
- Analyze tool capabilities without permission
- Understand tool arguments before governance approval
- Probe for sensitive functionality even in READ_ONLY mode

Security Requirements:
1. Blocked tools must NOT return schema
2. approval_required response must NOT include schema
3. Schema only returned when lease is successfully granted
"""


import pytest

pytestmark = pytest.mark.skip(reason="Phase 4 not yet implemented")


@pytest.mark.asyncio
async def test_blocked_tool_no_schema():
    """
    CRITICAL: Blocked tools must NOT return schema.

    Security Risk: Schema leakage allows analyzing tool arguments
    even when tool is blocked by governance.

    Attack Scenario:
    1. Mode is READ_ONLY
    2. Attacker calls get_tool_schema("write_file")
    3. Tool is blocked by governance
    4. Response should be error or status=blocked
    5. Response must NOT include inputSchema field

    This prevents reconnaissance attacks where attacker learns
    tool structure even when blocked.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode

    # Set mode to READ_ONLY
    # await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Request schema for write_file (should be blocked)
    # try:
    #     response = await get_tool_schema.fn(tool_name="write_file")
    #
    #     # If response is string, parse it
    #     if isinstance(response, str):
    #         response_data = json.loads(response)
    #     else:
    #         response_data = response
    #
    #     # Verify response indicates blocked status
    #     assert response_data.get("status") == "blocked" or \
    #            "blocked" in response_data.get("error", "").lower()
    #
    #     # CRITICAL: Verify no schema in response
    #     assert "inputSchema" not in response_data, \
    #            "SECURITY BREACH: Schema leaked for blocked tool!"
    #     assert "properties" not in response_data, \
    #            "SECURITY BREACH: Schema properties leaked for blocked tool!"
    #
    # except Exception as e:
    #     # Exception is acceptable (tool blocked)
    #     # But verify exception message doesn't leak schema
    #     error_msg = str(e)
    #     assert "properties" not in error_msg.lower()
    #     assert "inputSchema" not in error_msg



@pytest.mark.asyncio
async def test_approval_required_no_schema():
    """
    CRITICAL: approval_required response must NOT include schema.

    Security Risk: Schema in approval request leaks tool structure
    before user approves.

    Attack Scenario:
    1. Mode is PERMISSION
    2. Attacker calls get_tool_schema("write_file")
    3. Governance requires approval
    4. Response status=approval_required
    5. Response must NOT include inputSchema

    The schema should only be revealed AFTER approval is granted
    and lease is created.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode

    # Set mode to PERMISSION
    # await governance_state.set_mode(ExecutionMode.PERMISSION)

    # Request schema for sensitive tool (requires approval)
    # response = await get_tool_schema.fn(tool_name="write_file")

    # Parse response
    # if isinstance(response, str):
    #     response_data = json.loads(response)
    # else:
    #     response_data = response

    # If approval required
    # if response_data.get("status") == "approval_required":
    #     # CRITICAL: Verify no schema in response
    #     assert "inputSchema" not in response_data, \
    #            "SECURITY BREACH: Schema leaked in approval request!"
    #     assert "properties" not in response_data, \
    #            "SECURITY BREACH: Schema properties leaked in approval request!"
    #     assert "schema_min" not in response_data, \
    #            "SECURITY BREACH: Minimal schema leaked in approval request!"
    #
    #     # Response should include approval token instead
    #     assert "approval_token" in response_data or \
    #            "token" in response_data, \
    #            "approval_required response should include token"



@pytest.mark.asyncio
async def test_schema_only_after_lease_grant():
    """
    Verify schema is ONLY returned when lease is successfully granted.

    This is the positive test case: when authorization succeeds,
    schema should be included in response.
    """
    # TODO: Implement after Phase 3+4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode
    # from src.meta_mcp.leases import lease_manager

    # Set mode to BYPASS (auto-approve)
    # await governance_state.set_mode(ExecutionMode.BYPASS)

    # Request schema for read_file (safe tool)
    # response = await get_tool_schema.fn(tool_name="read_file")

    # Parse response
    # if isinstance(response, str):
    #     response_data = json.loads(response)
    # else:
    #     response_data = response

    # Verify schema is included
    # assert response_data.get("status") == "success"
    # assert "inputSchema" in response_data or "schema" in response_data, \
    #        "Schema should be included when lease granted"

    # Verify lease was created
    # lease = await lease_manager.validate("test_client_id", "read_file")
    # assert lease is not None, "Lease should be created when schema returned"



@pytest.mark.asyncio
async def test_schema_minimal_before_expansion():
    """
    Verify schema_min is returned initially, not full schema.

    Phase 5 feature: Progressive schemas start with minimal version
    and expand on demand.

    This test ensures full schema is not leaked in initial response.
    """
    # TODO: Implement after Phase 5
    # from src.meta_mcp.supervisor import get_tool_schema

    # Request schema for complex tool
    # response = await get_tool_schema.fn(tool_name="write_file")

    # if isinstance(response, str):
    #     response_data = json.loads(response)
    # else:
    #     response_data = response

    # if response_data.get("status") == "success":
    #     # Verify minimal schema returned
    #     schema = response_data.get("inputSchema") or response_data.get("schema")
    #
    #     # Estimate token count (rough)
    #     schema_str = json.dumps(schema)
    #     token_estimate = len(schema_str) / 4  # Rough estimate
    #
    #     # Should be under 50 tokens for minimal schema
    #     assert token_estimate < 200, \
    #            f"Initial schema too large: ~{token_estimate} tokens"
    #
    #     # Verify expansion_available flag
    #     assert response_data.get("expansion_available") is True, \
    #            "Should indicate full schema is available"



@pytest.mark.asyncio
async def test_error_message_no_schema_leak():
    """
    Verify error messages don't leak schema information.

    Even in error cases, schema details should not be exposed.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode

    # Set mode to READ_ONLY
    # await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Try to get schema for blocked tool
    # try:
    #     response = await get_tool_schema.fn(tool_name="write_file")
    #     fail("Should have raised error for blocked tool")
    # except Exception as e:
    #     error_msg = str(e).lower()
    #
    #     # Verify error message doesn't contain schema keywords
    #     assert "properties" not in error_msg, \
    #            "Error message leaked schema properties"
    #     assert "required" not in error_msg or "requires" in error_msg, \
    #            "Error message leaked schema required fields"
    #     assert "type" not in error_msg or "file" in error_msg, \
    #            "Error message leaked schema types"



@pytest.mark.asyncio
async def test_search_results_no_schema():
    """
    Verify search_tools response does not include schemas.

    search_tools should return metadata only (name, description, tags).
    Schemas are only revealed via get_tool_schema.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import search_tools

    # Search for tools
    # results = search_tools.fn(query="file")

    # Parse results
    # if isinstance(results, str):
    #     # Results are formatted text, check for schema keywords
    #     results_lower = results.lower()
    #     assert "inputschema" not in results_lower, \
    #            "Search results leaked inputSchema"
    #     assert "properties:" not in results_lower, \
    #            "Search results leaked schema properties"
    # else:
    #     # Results are structured, verify no schema fields
    #     for result in results:
    #         assert "inputSchema" not in result, \
    #                "Search result leaked inputSchema"
    #         assert "schema" not in result, \
    #                "Search result leaked schema"
    #         assert "properties" not in result, \
    #                "Search result leaked properties"



@pytest.mark.asyncio
async def test_bootstrap_tools_schema_always_available():
    """
    Verify bootstrap tools always return schema (no governance check).

    Bootstrap tools (search_tools, get_tool_schema) should always
    be accessible regardless of governance mode.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode

    # Set strict mode
    # await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Request schema for bootstrap tool
    # response = await get_tool_schema.fn(tool_name="search_tools")

    # if isinstance(response, str):
    #     response_data = json.loads(response)
    # else:
    #     response_data = response

    # Verify schema is returned
    # assert response_data.get("status") == "success"
    # assert "inputSchema" in response_data or "schema" in response_data, \
    #        "Bootstrap tools should always return schema"



@pytest.mark.asyncio
async def test_schema_stripped_from_denial_response():
    """
    CRITICAL: Ensure denial responses don't accidentally include schema.

    This tests the response construction code to verify schemas are
    explicitly stripped from denial/error responses.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode

    # Set mode to READ_ONLY
    # await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Request schema for write_file
    # response = await get_tool_schema.fn(tool_name="write_file")

    # Serialize response to check all fields
    # response_str = json.dumps(response) if not isinstance(response, str) else response

    # Check for any schema-related keywords in entire response
    # forbidden_keywords = [
    #     '"inputSchema"',
    #     '"properties"',
    #     '"required"',
    #     '"type": "object"',
    #     '"$schema"'
    # ]
    #
    # for keyword in forbidden_keywords:
    #     assert keyword not in response_str, \
    #            f"SECURITY BREACH: Schema keyword '{keyword}' found in denial response"



@pytest.mark.asyncio
async def test_partial_schema_leak_in_json():
    """
    CRITICAL: Check for partial schema leakage via JSON serialization.

    Sometimes schemas leak via nested JSON fields or error details.
    This test checks the entire response structure.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.supervisor import get_tool_schema
    # from src.meta_mcp.state import governance_state, ExecutionMode
    # import json

    # Set mode to READ_ONLY
    # await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Request schema for sensitive tool
    # response = await get_tool_schema.fn(tool_name="delete_file")

    # Parse and check every field recursively
    # def check_no_schema(obj, path="root"):
    #     if isinstance(obj, dict):
    #         for key, value in obj.items():
    #             # Check key names
    #             assert key not in ["inputSchema", "properties", "items"], \
    #                    f"Schema field '{key}' found at {path}.{key}"
    #             # Recurse
    #             check_no_schema(value, f"{path}.{key}")
    #     elif isinstance(obj, list):
    #         for i, item in enumerate(obj):
    #             check_no_schema(item, f"{path}[{i}]")
    #
    # if isinstance(response, str):
    #     response_data = json.loads(response)
    # else:
    #     response_data = response
    #
    # check_no_schema(response_data)



@pytest.mark.asyncio
async def test_schema_not_in_logs():
    """
    Verify schemas are not logged in error/debug messages.

    Even if schemas aren't returned to client, logging them could
    leak information through log aggregation systems.
    """
    # TODO: Implement after Phase 4
    # This test would need to capture log output and verify
    # no schema information is logged for blocked tools

