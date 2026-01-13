"""Tool call hooks for MetaMCP tooling gateway."""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import Context


class HookManager:
    """
    Manage pre/post tool call hooks.

    Hooks are no-ops by default and can be customized by overriding methods.
    """

    def before_tool_call(
        self, ctx: Context, tool_name: str, args: dict[str, Any]
    ) -> None:
        """
        Hook invoked before tool execution.

        Args:
            ctx: FastMCP context
            tool_name: Name of the tool being invoked
            args: Tool arguments
        """
        return None

    def after_tool_call(
        self,
        ctx: Context,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        error: Optional[BaseException],
    ) -> None:
        """
        Hook invoked after tool execution.

        Args:
            ctx: FastMCP context
            tool_name: Name of the tool being invoked
            args: Tool arguments
            result: Tool result (if successful)
            error: Exception instance if tool raised
        """
        return None


hook_manager = HookManager()
