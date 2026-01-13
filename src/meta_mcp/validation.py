"""
Supervisor compliance validation.

Validates that the supervisor configuration matches architectural requirements.
Runs at startup, logs warnings, does not block startup.

This module is a standalone validation assistant that checks:
- Bootstrap tool configuration matches discovery registry
- Tool exposure follows progressive discovery principles
- No accidental auto-exposure violations

All checks are non-blocking - they log warnings but allow startup to continue.
"""

from typing import Any, Set
from loguru import logger


async def validate_bootstrap_tools(mcp_instance: Any, tool_registry: Any) -> bool:
    """
    Validate that only bootstrap tools are exposed at startup.

    Checks that the supervisor's exposed tools match the discovery registry's
    get_bootstrap_tools() specification. This ensures progressive discovery
    is correctly implemented.

    Args:
        mcp_instance: FastMCP supervisor instance
        tool_registry: ToolRegistry instance

    Returns:
        True if validation passes, False if mismatch detected
    """
    # Get expected bootstrap tools from registry
    expected_bootstrap = set(tool_registry.get_bootstrap_tools())

    # Get actually exposed tools from supervisor
    try:
        actual_tools_list = await mcp_instance.get_tools()
        actual_exposed = set([tool.name for tool in actual_tools_list.values()])
    except Exception as e:
        logger.error(f"Failed to get tool list for validation: {e}")
        return False

    # Compare expected vs actual
    if actual_exposed == expected_bootstrap:
        logger.info(
            f"✓ Bootstrap validation PASSED: {len(actual_exposed)} tools exposed "
            f"({', '.join(sorted(actual_exposed))})"
        )
        return True
    else:
        # Calculate differences
        extra_tools = actual_exposed - expected_bootstrap
        missing_tools = expected_bootstrap - actual_exposed

        # Log detailed warning
        logger.warning("=" * 60)
        logger.warning("⚠ BOOTSTRAP VALIDATION FAILED")
        logger.warning("=" * 60)
        logger.warning(f"Expected tools: {sorted(expected_bootstrap)}")
        logger.warning(f"Actual tools:   {sorted(actual_exposed)}")

        if extra_tools:
            logger.warning(f"Extra tools (should not be exposed): {sorted(extra_tools)}")
            logger.warning(
                "  → These tools violate progressive discovery!"
            )

        if missing_tools:
            logger.warning(f"Missing tools (should be exposed): {sorted(missing_tools)}")
            logger.warning(
                "  → Bootstrap tools are missing from supervisor!"
            )

        logger.warning("")
        logger.warning("Action required:")
        logger.warning("  1. Check supervisor.py @mcp.tool() decorators")
        logger.warning("  2. Verify tool_registry.get_bootstrap_tools()")
        logger.warning("  3. Ensure no mcp.mount() calls are active")
        logger.warning("=" * 60)

        return False


async def validate_no_auto_mounts(mcp_instance: Any) -> bool:
    """
    Validate that no servers are auto-mounted (would violate progressive discovery).

    This is a future placeholder for validating that core_server and admin_server
    are not mounted, which would auto-expose all 13 tools.

    Args:
        mcp_instance: FastMCP supervisor instance

    Returns:
        True (placeholder - always passes for now)
    """
    # TODO: Implement mount detection if FastMCP exposes this information
    # For now, we rely on bootstrap tool count validation
    return True


async def run_all_validations(mcp_instance: Any, tool_registry: Any) -> dict[str, bool]:
    """
    Run all validation checks.

    Convenience function to run all validation checks at startup.

    Args:
        mcp_instance: FastMCP supervisor instance
        tool_registry: ToolRegistry instance

    Returns:
        Dictionary of validation results {check_name: passed}
    """
    results = {}

    logger.info("Running supervisor compliance validations...")

    # Bootstrap tools validation
    results["bootstrap_tools"] = await validate_bootstrap_tools(
        mcp_instance, tool_registry
    )

    # Auto-mount validation
    results["no_auto_mounts"] = await validate_no_auto_mounts(mcp_instance)

    # Summary
    passed = sum(results.values())
    total = len(results)

    if passed == total:
        logger.info(f"✓ All validations passed ({passed}/{total})")
    else:
        logger.warning(f"⚠ {total - passed}/{total} validations failed")

    return results
