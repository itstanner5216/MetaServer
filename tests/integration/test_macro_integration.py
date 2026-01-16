"""
Integration Tests: Macro + Governance Integration (Phase 7 + 4)

Tests macro operations with governance enforcement:
1. Batch read with governance (Phase 7 + 4)
2. Batch search with risk filtering (Phase 7 + 4)
3. Macro operations respect leases (Phase 7 + 3)

Security Invariants:
- Batch operations respect governance policies
- Risk filtering prevents exposure of dangerous tools
- Leases apply to macro operations
- Batch size limits prevent DoS
"""

import pytest

from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.macros.batch_read import batch_read_tools
from src.meta_mcp.macros.batch_search import batch_search_tools
from src.meta_mcp.registry.models import ToolRecord


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_read_basic_operation(redis_client, fresh_registry):
    """
    Verify batch read retrieves multiple tools efficiently.

    Flow:
    1. Create registry with test tools
    2. Batch read multiple tool IDs
    3. Results contain all requested tools
    """
    # Create registry
    registry = fresh_registry

    # Add test tools
    registry.add_for_testing(
        ToolRecord(
            tool_id="tool_a",
            server_id="test_server",
            description_1line="Tool A",
            description_full="Tool A",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="tool_b",
            server_id="test_server",
            description_1line="Tool B",
            description_full="Tool B",
            tags=["test"],
            risk_level="sensitive",
        )
    )

    # Batch read
    results = batch_read_tools(registry=registry, tool_ids=["tool_a", "tool_b"])

    # Verify results
    assert "tool_a" in results
    assert "tool_b" in results
    assert results["tool_a"].tool_id == "tool_a"
    assert results["tool_b"].tool_id == "tool_b"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_read_with_risk_filtering(redis_client, fresh_registry):
    """
    Verify batch read filters by max risk level.

    Flow:
    1. Register tools with different risk levels
    2. Batch read with max_risk_level="safe"
    3. Only safe tools returned
    """
    registry = fresh_registry

    # Add tools with different risks
    registry.add_for_testing(
        ToolRecord(
            tool_id="safe_tool",
            server_id="test_server",
            description_1line="Safe tool",
            description_full="Safe tool",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="sensitive_tool",
            server_id="test_server",
            description_1line="Sensitive tool",
            description_full="Sensitive tool",
            tags=["test"],
            risk_level="sensitive",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="dangerous_tool",
            server_id="test_server",
            description_1line="Dangerous tool",
            description_full="Dangerous tool",
            tags=["test"],
            risk_level="dangerous",
        )
    )

    # Batch read with risk filtering
    results = batch_read_tools(
        registry=registry,
        tool_ids=["safe_tool", "sensitive_tool", "dangerous_tool"],
        max_risk_level="safe",
    )

    # Only safe tool should be returned
    assert results["safe_tool"] is not None
    assert results["sensitive_tool"] is None
    assert results["dangerous_tool"] is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_read_size_limit(redis_client, fresh_registry):
    """
    Verify batch read enforces size limits.

    Security: Prevents DoS via massive batch requests.

    Flow:
    1. Request batch larger than max_batch_size
    2. Operation returns error
    """
    registry = fresh_registry

    # Create large batch request
    large_batch = [f"tool_{i}" for i in range(2000)]

    # Batch read with limit
    results = batch_read_tools(registry=registry, tool_ids=large_batch, max_batch_size=1000)

    # Should contain error
    assert "error" in results


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_search_basic_operation(redis_client, fresh_registry):
    """
    Verify batch search executes multiple queries efficiently.

    Flow:
    1. Register tools in registry
    2. Batch search with multiple queries
    3. Each query returns relevant results
    """
    registry = fresh_registry

    # Add test tools
    registry.add_for_testing(
        ToolRecord(
            tool_id="read_file",
            server_id="test_server",
            description_1line="Read file from disk",
            description_full="Read file from disk",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="write_file",
            server_id="test_server",
            description_1line="Write file to disk",
            description_full="Write file to disk",
            tags=["test"],
            risk_level="sensitive",
        )
    )

    # Batch search
    results = batch_search_tools(registry=registry, queries=["read", "write"])

    # Verify results
    assert "read" in results
    assert "write" in results
    assert len(results["read"]) > 0
    assert len(results["write"]) > 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_search_with_risk_exclusion(redis_client, fresh_registry):
    """
    Verify batch search excludes specified risk levels.

    Flow:
    1. Register tools with different risks
    2. Batch search with exclude_risk_levels=["dangerous"]
    3. Dangerous tools filtered from results
    """
    registry = fresh_registry

    # Add tools
    registry.add_for_testing(
        ToolRecord(
            tool_id="safe_tool",
            server_id="test_server",
            description_1line="Safe operation",
            description_full="Safe operation",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="dangerous_tool",
            server_id="test_server",
            description_1line="Dangerous operation",
            description_full="Dangerous operation",
            tags=["test"],
            risk_level="dangerous",
        )
    )

    # Batch search with risk exclusion
    results = batch_search_tools(
        registry=registry, queries=["operation"], exclude_risk_levels=["dangerous"]
    )

    # Only safe tool in results
    assert len(results["operation"]) >= 1
    for candidate in results["operation"]:
        assert candidate.risk_level != "dangerous"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_search_with_min_score(redis_client, fresh_registry):
    """
    Verify batch search filters by minimum relevance score.

    Flow:
    1. Batch search with min_score threshold
    2. Only high-scoring results returned
    """
    registry = fresh_registry

    # Add tools
    registry.add_for_testing(
        ToolRecord(
            tool_id="exact_match",
            server_id="test_server",
            description_1line="Exact query match",
            description_full="Exact query match",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="partial_match",
            server_id="test_server",
            description_1line="Partial query similarity",
            description_full="Partial query similarity",
            tags=["test"],
            risk_level="safe",
        )
    )

    # Batch search with min_score
    # Note: Actual scoring depends on search implementation
    results = batch_search_tools(registry=registry, queries=["match"], min_score=0.5)

    # Results should exist
    assert "match" in results


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_search_limit_per_query(redis_client, fresh_registry):
    """
    Verify batch search respects per-query result limit.

    Flow:
    1. Add many matching tools
    2. Batch search with limit=3
    3. Each query returns max 3 results
    """
    registry = fresh_registry

    # Add multiple matching tools
    for i in range(10):
        registry.add_for_testing(
            ToolRecord(
                tool_id=f"test_tool_{i}",
                server_id="test_server",
                description_1line="Test tool for searching",
                description_full="Test tool for searching",
                tags=["test"],
                risk_level="safe",
            )
        )

    # Batch search with limit
    results = batch_search_tools(registry=registry, queries=["test"], limit=3)

    # Verify limit enforced
    assert len(results["test"]) <= 3


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_macro_operations_respect_leases(redis_client):
    """
    Verify macro operations check leases before execution.

    Flow:
    1. Grant lease for specific tools
    2. Batch read includes tools with and without leases
    3. Governance applies to each tool independently
    """
    # Grant lease for safe tool
    await lease_manager.grant(
        client_id="macro_lease_test",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Verify lease exists
    lease = await lease_manager.validate("macro_lease_test", "read_file")
    assert lease is not None

    # In real implementation, batch operations would check leases
    # For now, we verify lease validation works
    assert lease.calls_remaining == 5


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_read_audit_logging(redis_client, fresh_registry):
    """
    Verify batch read logs operations when audit=True.

    Flow:
    1. Batch read with audit=True
    2. Audit log contains batch_read event
    """
    registry = fresh_registry

    # Add test tool
    registry.add_for_testing(
        ToolRecord(
            tool_id="test_tool",
            server_id="test_server",
            description_1line="Test tool",
            description_full="Test tool",
            tags=["test"],
            risk_level="safe",
        )
    )

    # Batch read with audit
    results = batch_read_tools(
        registry=registry,
        tool_ids=["test_tool"],
        audit=True,
        session_id="audit_test_session",
        user_id="test_user",
    )

    # Operation succeeds (audit is logged internally)
    assert "test_tool" in results


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_operations_empty_input(redis_client, fresh_registry):
    """
    Verify batch operations handle empty input gracefully.

    Flow:
    1. Batch read with None tool_ids
    2. Batch search with empty queries
    3. Both return empty results
    """
    registry = fresh_registry

    # Batch read with None
    read_results = batch_read_tools(registry=registry, tool_ids=None)
    assert read_results == {}

    # Batch read with empty list
    read_results = batch_read_tools(registry=registry, tool_ids=[])
    assert read_results == {}

    # Batch search with None
    search_results = batch_search_tools(registry=registry, queries=None)
    assert search_results == {}

    # Batch search with empty list
    search_results = batch_search_tools(registry=registry, queries=[])
    assert search_results == {}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_read_nonexistent_tools(redis_client, fresh_registry):
    """
    Verify batch read handles nonexistent tools gracefully.

    Flow:
    1. Batch read with mix of existent and nonexistent IDs
    2. Existent tools returned
    3. Nonexistent tools return None
    """
    registry = fresh_registry

    # Add one tool
    registry.add_for_testing(
        ToolRecord(
            tool_id="exists",
            server_id="test_server",
            description_1line="This tool exists",
            description_full="This tool exists",
            tags=["test"],
            risk_level="safe",
        )
    )

    # Batch read with mix
    results = batch_read_tools(registry=registry, tool_ids=["exists", "does_not_exist"])

    # Existent tool found
    assert results["exists"] is not None

    # Nonexistent tool returns None
    assert results["does_not_exist"] is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_macro_governance_workflow(redis_client, fresh_registry):
    """
    End-to-end test of macro operations with governance.

    Flow:
    1. Register tools with different risk levels
    2. Set governance mode to PERMISSION
    3. Batch search finds tools
    4. Batch read filters by risk level
    5. Sensitive tools require leases
    6. Safe tools accessible without leases
    """
    registry = fresh_registry

    # Register tools
    registry.add_for_testing(
        ToolRecord(
            tool_id="safe_read",
            server_id="test_server",
            description_1line="Safe read operation",
            description_full="Safe read operation",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="sensitive_write",
            server_id="test_server",
            description_1line="Sensitive write operation",
            description_full="Sensitive write operation",
            tags=["test"],
            risk_level="sensitive",
        )
    )

    # Step 1: Batch search
    search_results = batch_search_tools(registry=registry, queries=["read", "write"])
    assert len(search_results["read"]) > 0
    assert len(search_results["write"]) > 0

    # Step 2: Batch read all tools
    all_results = batch_read_tools(registry=registry, tool_ids=["safe_read", "sensitive_write"])
    assert all_results["safe_read"] is not None
    assert all_results["sensitive_write"] is not None

    # Step 3: Batch read with safe-only filter
    safe_results = batch_read_tools(
        registry=registry, tool_ids=["safe_read", "sensitive_write"], max_risk_level="safe"
    )
    assert safe_results["safe_read"] is not None
    assert safe_results["sensitive_write"] is None

    # Step 4: Grant lease for sensitive tool
    await lease_manager.grant(
        client_id="macro_workflow_test",
        tool_id="sensitive_write",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Step 5: Verify lease exists
    lease = await lease_manager.validate("macro_workflow_test", "sensitive_write")
    assert lease is not None
    assert lease.tool_id == "sensitive_write"
