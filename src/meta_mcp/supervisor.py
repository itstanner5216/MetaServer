"""Main FastMCP supervisor server with governance middleware and discovery tools."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from loguru import logger

from servers.admin_tools import admin_server
from servers.core_tools import core_server

from .audit import audit_logger
from .config import Config
from .context import build_run_context
from .discovery import format_search_results
from .governance.approval import get_approval_provider
from .governance.artifacts import get_artifact_generator
from .governance.policy import evaluate_policy
from .governance.tokens import generate_token
from .leases import lease_manager
from .registry import tool_registry
from .middleware import GovernanceMiddleware
from .state import governance_state
from .validation import run_all_validations


# Constants
SERVER_NAME = "MetaSupervisor"
HOST = Config.HOST
PORT = Config.PORT
WORKSPACE_ROOT = Config.WORKSPACE_ROOT


# ============================================================================
# DYNAMIC TOOL REGISTRY
# ============================================================================
# Module-level state for progressive discovery:
# - _loaded_tools: Tracks which tools have been exposed via tools/list endpoint
# - _tool_instances: Caches tool function instances to avoid re-importing
#
# Tools are exposed on-demand via _expose_tool() rather than auto-mounted.
# This implements context minimization by only exposing tools as they are requested.
# ============================================================================

_loaded_tools: set[str] = set()  # Tools currently exposed to MCP clients
_tool_instances: dict[str, Any] = {}  # Cached tool function instances


async def _get_tool_function(tool_name: str) -> Optional[Any]:
    """
    Lazily retrieve FunctionTool instance from core_server or admin_server.

    Uses the async get_tool() method to retrieve the FunctionTool wrapper
    from the mounted server instances. Caches tool instances to avoid
    repeated async lookups.

    Args:
        tool_name: Name of the tool to retrieve

    Returns:
        FunctionTool instance if found, None otherwise
    """
    # Check cache first
    if tool_name in _tool_instances:
        return _tool_instances[tool_name]

    # Define tool mappings
    core_tools = {
        "read_file",
        "write_file",
        "delete_file",
        "list_directory",
        "create_directory",
        "remove_directory",
        "move_file",
        "execute_command",
        "git_commit",
        "git_push",
        "git_reset",
    }

    admin_tools = {
        "set_governance_mode",
        "get_governance_status",
        "revoke_all_elevations",
    }

    # Try to get FunctionTool from core_server
    if tool_name in core_tools:
        tool_instance = await core_server.get_tool(tool_name)
        if tool_instance:
            _tool_instances[tool_name] = tool_instance
            return tool_instance

    # Try to get FunctionTool from admin_server
    if tool_name in admin_tools:
        tool_instance = await admin_server.get_tool(tool_name)
        if tool_instance:
            _tool_instances[tool_name] = tool_instance
            return tool_instance

    # Tool not recognized
    return None


async def _expose_tool(tool_name: str) -> bool:
    """
    Dynamically expose a tool to MCP clients.

    Implements progressive discovery by registering tools on-demand
    rather than auto-exposing all tools at startup.

    Args:
        tool_name: Name of the tool to expose

    Returns:
        True if tool was exposed successfully, False otherwise
    """
    # Check if already exposed (either via _loaded_tools or as bootstrap tool)
    if tool_name in _loaded_tools:
        logger.debug(f"Tool '{tool_name}' already exposed, skipping")
        return True

    # Check if tool is a bootstrap tool (already auto-exposed via @mcp.tool())
    bootstrap_tools = tool_registry.get_bootstrap_tools()
    if tool_name in bootstrap_tools:
        logger.debug(f"Tool '{tool_name}' is a bootstrap tool, already auto-exposed")
        return True

    # Verify tool exists in discovery registry
    if not tool_registry.is_registered(tool_name):
        logger.warning(f"Tool '{tool_name}' not found in discovery registry")
        return False

    # Get FunctionTool instance from server
    tool_instance = await _get_tool_function(tool_name)
    if not tool_instance:
        logger.error(f"Failed to retrieve FunctionTool for '{tool_name}'")
        return False

    # Register tool with FastMCP supervisor
    try:
        mcp.add_tool(tool_instance)
        _loaded_tools.add(tool_name)
        logger.info(f"Dynamically exposed tool: {tool_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to expose tool '{tool_name}': {e}")
        return False


# ============================================================================
# LIFECYCLE MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app):
    """
    Server lifecycle manager (startup/shutdown).

    Startup:
    1. Redis connectivity verification (graceful degradation to PERMISSION mode)
    2. Core tools registration in discovery registry
    3. Workspace directory creation
    4. Compliance validations (bootstrap tools, progressive discovery)
    5. Approval provider health check
    6. Artifact generator initialization
    7. Startup logging

    Shutdown:
    - Clean shutdown logging
    """
    # STARTUP
    logger.info(f"Starting {SERVER_NAME} server...")

    # 1. Verify Redis connectivity (graceful degradation)
    try:
        mode = await governance_state.get_mode()
        logger.info(f"Redis connected - Governance mode: {mode.value}")
    except Exception as e:
        logger.warning(
            f"Redis connection failed during startup: {e}. "
            "Degrading to PERMISSION mode (fail-safe default)."
        )
        # governance_state.get_mode() already handles fail-safe to PERMISSION
        # No need to crash - system will operate in PERMISSION mode

    # 2. Register core tools in discovery registry
    # (Already done via auto-registration in discovery.py on import)
    all_tools = tool_registry.get_all_summaries()
    logger.info(f"Tool registry initialized with {len(all_tools)} tools")

    # 3. Ensure workspace directory exists
    workspace_path = Path(WORKSPACE_ROOT)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory ready: {workspace_path.resolve()}")

    # 4. Run compliance validations (non-blocking)
    await run_all_validations(mcp, tool_registry)

    # 5. Approval provider health check
    try:
        # Initialize approval provider and check availability
        provider = await get_approval_provider(context=None)
        is_available = await provider.is_available()

        if is_available:
            logger.info(
                f"Approval provider: {provider.get_name()} - AVAILABLE ✓"
            )
        else:
            logger.warning(
                f"Approval provider: {provider.get_name()} - NOT AVAILABLE (will retry at runtime)"
            )

    except Exception as e:
        logger.error(
            f"Approval provider initialization failed: {e}. "
            "Sensitive operations will fail in PERMISSION mode. "
            "Check logs for details or ensure approval provider dependencies are installed."
        )

    # 6. Artifact generator initialization
    try:
        artifact_generator = get_artifact_generator()
        logger.info(
            f"Artifact generator initialized: {artifact_generator.artifacts_root}"
        )
    except Exception as e:
        logger.error(
            f"Artifact generator initialization failed: {e}. "
            "Approval artifacts will not be generated."
        )

    # 7. Log startup completion
    logger.info(f"{SERVER_NAME} startup complete")
    logger.info(f"Listening on {HOST}:{PORT}")
    logger.info(f"Governance middleware: ACTIVE")
    logger.info(f"Audit logging: {audit_logger.log_path}")

    yield  # Server runs here

    # SHUTDOWN
    logger.info(f"{SERVER_NAME} shutting down...")
    await governance_state.close()


# Create FastMCP instance with governance middleware and lifecycle
# NOTE: GovernanceMiddleware is the ONLY middleware - it handles all enforcement
mcp = FastMCP(name=SERVER_NAME, middleware=[GovernanceMiddleware()], lifespan=lifespan)


# ============================================================================
# MOUNT CONFIGURATION - DISABLED FOR PROGRESSIVE DISCOVERY
# ============================================================================
# DO NOT mount servers - this auto-exposes all tools immediately, violating
# context minimization principles. Tools will be registered dynamically via
# progressive discovery as they are requested.
#
# Previously auto-exposed tools (13 total):
# - core_server (10): read_file, write_file, delete_file, list_directory,
#                     create_directory, move_file, execute_command,
#                     git_commit, git_push, git_reset
# - admin_server (3): set_governance_mode, get_governance_status,
#                     revoke_all_elevations
#
# Tools will now be exposed on-demand via _expose_tool() function below.
# ============================================================================

# DEPRECATED: Auto-exposure via mount() - DO NOT UNCOMMENT
# mcp.mount(core_server)   # Would expose all 10 core tools immediately
# mcp.mount(admin_server)  # Would expose all 3 admin tools immediately


# ============================================================================
# DISCOVERY TOOLS (Control Plane Only)
# ============================================================================

@mcp.tool()
def search_tools(query: str) -> str:
    """
    Search for available tools by name or description.

    Returns static metadata only:
    - Tool name
    - One-sentence description
    - Sensitivity flag

    Does NOT return:
    - Arguments or schemas
    - Examples or usage hints
    - Rankings or recommendations

    Args:
        query: Search query string

    Returns:
        Formatted list of matching tools with metadata
    """
    if not query or not query.strip():
        return "Error: Query cannot be empty. Please provide a search term."

    # Search tool registry
    results = tool_registry.search(query)

    # Format results for agent consumption
    return format_search_results(results)


@mcp.tool()
async def get_tool_schema(tool_name: str, expand: bool = False, ctx: Context = None) -> str:
    """
    Get JSON schema for a specific tool (PROGRESSIVE DISCOVERY TRIGGER).

    This function is the trigger point for progressive discovery. When a model
    requests a tool's schema, this function:
    1. Validates the tool exists in the discovery registry
    2. Dynamically exposes the tool to MCP clients (adds to tools/list)
    3. Returns the JSON schema (minimal or full based on expand parameter)

    Tools are ONLY visible in tools/list AFTER this function is called.
    This implements context minimization by exposing tools on-demand rather
    than auto-exposing all tools at startup.

    Workflow:
    - Model searches for tools using search_tools() → gets metadata only
    - Model requests schema using get_tool_schema() → tool is exposed + schema returned
    - Tool now appears in tools/list and can be invoked
    - Model can request full schema using get_tool_schema(expand=True) if needed

    Args:
        tool_name: Name of the tool to get schema for
        expand: If True, return full schema; if False, return minimal schema (default: False)

    Returns:
        JSON schema with name, description, and inputSchema fields

    Raises:
        ToolError: If tool is not registered or exposure fails
    """
    # Step 1: Validate tool is registered in discovery registry
    if not tool_registry.is_registered(tool_name):
        raise ToolError(f"Tool '{tool_name}' is not registered")

    # Step 2: PROGRESSIVE DISCOVERY TRIGGER - Expose tool to MCP clients
    # This adds the tool to tools/list and makes it available for invocation
    if not await _expose_tool(tool_name):
        raise ToolError(
            f"Failed to expose tool '{tool_name}'. "
            "Tool may not exist in core_server or admin_server."
        )

    # Step 2.5: PHASE 3+4 INTEGRATION - Evaluate policy and grant lease
    # Extract client_id from FastMCP session context
    # In FastMCP/MCP protocol, session_id is the stable client connection identifier
    # If context is not available (shouldn't happen), fail closed with safe default
    run_context = build_run_context(ctx) if ctx else None
    if ctx is not None:
        ctx.run_context = run_context

    if ctx is None:
        logger.warning(
            f"No context available for get_tool_schema({tool_name}), using fail-safe client_id"
        )
        client_id = "unknown_client"  # Fail-safe: each call gets unique lease
    else:
        client_id = str(ctx.session_id)

    # Get tool metadata from registry to determine risk level
    tool_record = tool_registry.get(tool_name)
    if not tool_record:
        raise ToolError(f"Tool '{tool_name}' not found in registry")

    risk_level = tool_record.risk_level

    # Get current governance mode
    current_mode = await governance_state.get_mode()

    # PHASE 4: Evaluate governance policy
    policy_decision = evaluate_policy(
        mode=current_mode,
        tool_risk=risk_level,
        tool_id=tool_name,
    )

    # Handle policy decision
    if policy_decision.action == "block":
        # Policy blocks access - deny immediately
        logger.warning(
            f"Policy blocked access to '{tool_name}': {policy_decision.reason}"
        )
        raise ToolError(
            f"Access to '{tool_name}' blocked by policy: {policy_decision.reason}"
        )

    elif policy_decision.action == "require_approval":
        # Policy requires approval - trigger elicitation
        # NOTE: This uses the existing middleware elicitation pattern
        # The middleware will handle approval request and elevation grant
        logger.info(
            f"Policy requires approval for '{tool_name}': {policy_decision.reason}"
        )
        raise ToolError(
            f"Access to '{tool_name}' requires approval. "
            f"The system will prompt for permission when you attempt to use this tool. "
            f"Reason: {policy_decision.reason}"
        )

    # Policy allows access - proceed with lease grant
    logger.info(f"Policy allows access to '{tool_name}': {policy_decision.reason}")

    # Determine TTL and calls based on risk level
    ttl_seconds = Config.LEASE_TTL_BY_RISK.get(risk_level, 300)
    calls_remaining = Config.LEASE_CALLS_BY_RISK.get(risk_level, 1)

    # PHASE 4: Generate capability token
    capability_token = generate_token(
        client_id=client_id,
        tool_id=tool_name,
        ttl_seconds=ttl_seconds,
        secret=Config.HMAC_SECRET,
        context_key=None,  # No additional context scoping for now
    )

    # Grant lease with capability token
    lease = await lease_manager.grant(
        client_id=client_id,
        tool_id=tool_name,
        ttl_seconds=ttl_seconds,
        calls_remaining=calls_remaining,
        mode_at_issue=current_mode.value,
        capability_token=capability_token,
    )

    # Fail-safe: Deny access if lease grant fails
    if lease is None:
        raise ToolError(
            f"Failed to grant lease for '{tool_name}'. "
            "Access denied due to lease management failure."
        )

    logger.info(
        f"Granted lease for {client_id}:{tool_name} "
        f"(TTL={ttl_seconds}s, calls={calls_remaining}, mode={current_mode.value}, "
        f"policy={policy_decision.action})"
    )

    # Step 3: Retrieve tool from MCP registry (now exposed)
    try:
        tool = await mcp.get_tool(tool_name)

        if not tool:
            raise ToolError(
                f"Tool '{tool_name}' not found in MCP registry after exposure"
            )

        # Step 4: Convert to MCP format and extract schema
        mcp_tool = tool.to_mcp_tool()

        # Step 5: Get schema (minimal or full based on expand parameter)
        input_schema = mcp_tool.inputSchema if mcp_tool.inputSchema else {}

        # Phase 5: Progressive Schemas - Return minimal or full based on expand parameter
        if expand:
            # expand=True: Always return full schema, bypass minimization
            # Get full schema from registry if available
            tool_record = tool_registry.get(tool_name)
            if tool_record and tool_record.schema_full:
                input_schema = tool_record.schema_full
            # else: use current input_schema from mcp_tool
        elif Config.ENABLE_PROGRESSIVE_SCHEMAS:
            # expand=False and progressive schemas enabled: Return minimal schema
            from .schemas import minimize_schema

            # Store full schema in registry for later expansion
            tool_record = tool_registry.get(tool_name)
            if tool_record and not tool_record.schema_full:
                tool_record.schema_full = input_schema
                tool_record.schema_min = minimize_schema(input_schema)

            # Return minimal schema
            if tool_record and tool_record.schema_min:
                input_schema = tool_record.schema_min

        # Step 6: Return formatted JSON schema
        return json.dumps(
            {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "inputSchema": input_schema,
            },
            indent=2,
        )

    except Exception as e:
        raise ToolError(f"Failed to get schema for '{tool_name}': {e}")


# DEPRECATED: expand_tool_schema tool removed in favor of expand parameter
# Use get_tool_schema(tool_name="X", expand=True) instead of expand_tool_schema(tool_name="X")
# This consolidates schema retrieval into a single tool with an optional parameter,
# reducing API surface area and improving discoverability.


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """
    Main entry point for the supervisor server.

    Configures:
    - Loguru for structured logging
    - HTTP/SSE transport for Docker compatibility
    - Async event loop
    """
    # Configure loguru for supervisor logging
    logger.remove()  # Remove default handler

    # Add console handler with structured format
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level="INFO",
    )

    # Add file handler for supervisor logs
    logger.add(
        "supervisor.log",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        level="DEBUG",
    )

    logger.info(f"Starting {SERVER_NAME}...")

    # Run with HTTP/SSE transport (Docker compatible)
    try:
        mcp.run(transport="sse", host=HOST, port=PORT)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
