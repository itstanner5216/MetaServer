"""Helpers for constructing approval requests."""

import hashlib
import time
from typing import Any, Dict, List, Optional

from fastmcp import Context
from loguru import logger

from ..config import Config
from ..registry import tool_registry
from .approval import ApprovalRequest
from .artifacts import get_artifact_generator


def extract_context_key(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Extract context key for scoped elevation.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        Context key (path for file ops, command[:50] for commands)
    """
    # Move operation: use source path (MUST check BEFORE general file ops)
    if tool_name == "move_file":
        return arguments.get("source", "unknown")

    # File operations: use path
    if tool_name in {
        "write_file",
        "delete_file",
        "read_file",
    }:
        return arguments.get("path", "unknown")

    # Directory operations: use path
    if tool_name in {"create_directory", "remove_directory", "list_directory"}:
        return arguments.get("path", "unknown")

    # Command execution: use first 50 chars of command
    if tool_name == "execute_command":
        command = arguments.get("command", "unknown")
        return command[:50] if len(command) > 50 else command

    # Git operations: use current directory
    if tool_name.startswith("git_"):
        return arguments.get("cwd", ".")

    # Admin operations: use operation name
    if tool_name in {"set_governance_mode", "revoke_all_elevations"}:
        return tool_name

    # Default: tool name
    return tool_name


def generate_request_id(session_id: str, tool_name: str, context_key: str) -> str:
    """
    Generate stable request ID for approval requests.

    Format: {session_id_hash}_{tool_name}_{context_hash}_{timestamp_ms}

    Args:
        session_id: Session identifier
        tool_name: Name of the tool
        context_key: Context key (path, command, etc.)

    Returns:
        Stable request ID for this approval request
    """
    # Hash session_id for privacy (first 8 chars)
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:8]

    # Hash context_key to keep request_id readable (first 8 chars)
    context_hash = hashlib.sha256(context_key.encode()).hexdigest()[:8]

    # Use monotonic timestamp in milliseconds for uniqueness
    timestamp_ms = int(time.monotonic() * 1000)

    return f"{session_hash}_{tool_name}_{context_hash}_{timestamp_ms}"


def get_required_scopes(tool_name: str, arguments: Dict[str, Any]) -> List[str]:
    """
    Get required permission scopes for a tool operation.

    Fetches base scopes from tool registry metadata, then adds
    resource-specific scopes based on tool arguments (e.g., specific file paths).

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        List of required permission scopes
    """
    # Start with base scopes from registry
    tool_record = tool_registry.get_tool(tool_name)
    if tool_record and tool_record.required_scopes:
        base_scopes = tool_record.required_scopes.copy()
    else:
        # Fallback: generate basic scope if not in registry
        logger.warning(
            f"Tool {tool_name} not found in registry or has no required_scopes, "
            f"using fallback scope"
        )
        base_scopes = [f"tool:{tool_name}"]

    # Add resource-specific scopes based on arguments
    # These are dynamic and depend on actual operation context
    if tool_name in {"write_file", "delete_file", "read_file"}:
        path = arguments.get("path", "")
        if path:
            base_scopes.append(f"resource:path:{path}")

    elif tool_name == "move_file":
        source = arguments.get("source", "")
        dest = arguments.get("destination", "")
        if source:
            base_scopes.append(f"resource:path:{source}")
        if dest:
            base_scopes.append(f"resource:path:{dest}")

    elif tool_name == "execute_command":
        command = arguments.get("command", "")
        if command:
            # Add specific command being executed (first 50 chars)
            cmd_preview = command[:50] if len(command) > 50 else command
            base_scopes.append(f"resource:command:{cmd_preview}")

    elif tool_name in {"create_directory", "list_directory"}:
        path = arguments.get("path", "")
        if path:
            base_scopes.append(f"resource:path:{path}")

    return base_scopes


def format_approval_request(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Format approval request in Markdown.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        Formatted approval request
    """
    lines = [
        "# Approval Required",
        "",
        f"**Tool:** `{tool_name}`",
        "",
        "**Arguments:**",
    ]

    for key, value in arguments.items():
        # Truncate long values
        value_str = str(value)
        if len(value_str) > 200:
            value_str = value_str[:200] + "..."
        lines.append(f"- `{key}`: {value_str}")

    lines.extend(
        [
            "",
            "**Actions:**",
            "- Type `approve` to execute",
            "- Type `deny` to reject",
            "",
            "This approval will grant scoped elevation for "
            f"{Config.DEFAULT_ELEVATION_TTL} seconds.",
        ]
    )

    return "\n".join(lines)


def build_permission_request(
    ctx: Context, tool_name: str, arguments: Dict[str, Any]
) -> ApprovalRequest:
    """
    Build an ApprovalRequest with generated metadata and artifacts.

    Args:
        ctx: FastMCP context
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        ApprovalRequest with precomputed request_id, message, scopes, and artifacts.
    """
    session_id = str(ctx.session_id)
    context_key = extract_context_key(tool_name, arguments)
    request_id = generate_request_id(session_id, tool_name, context_key)
    required_scopes = get_required_scopes(tool_name, arguments)
    request_message = format_approval_request(tool_name, arguments)

    artifacts_path: Optional[str] = None
    try:
        artifact_generator = get_artifact_generator()

        # Generate HTML artifact for GUI display
        html_path = artifact_generator.generate_html_artifact(
            request_id=request_id,
            tool_name=tool_name,
            message=request_message,
            required_scopes=required_scopes,
            arguments=arguments,
            context_metadata={
                "session_id": session_id,
                "context_key": context_key,
            },
        )

        # Generate JSON artifact for programmatic access
        json_path = artifact_generator.generate_json_artifact(
            request_id=request_id,
            tool_name=tool_name,
            message=request_message,
            required_scopes=required_scopes,
            arguments=arguments,
            context_metadata={
                "session_id": session_id,
                "context_key": context_key,
            },
        )

        # Use HTML path for UI (JSON available at same location with .json extension)
        artifacts_path = html_path
        logger.debug(
            f"Generated approval artifacts for {request_id}: "
            f"HTML={html_path}, JSON={json_path}"
        )

    except Exception as e:
        # Non-fatal: approval can proceed without artifacts
        logger.warning(f"Failed to generate approval artifacts for {request_id}: {e}")

    return ApprovalRequest(
        request_id=request_id,
        tool_name=tool_name,
        message=request_message,
        required_scopes=required_scopes,
        artifacts_path=artifacts_path,
        timeout_seconds=Config.ELICITATION_TIMEOUT,
        context_metadata={
            "session_id": session_id,
            "arguments": arguments,
            "context_key": context_key,
        },
    )
