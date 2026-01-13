"""Hook system for tool execution lifecycle."""

from typing import Any, Dict

from fastmcp import Context


class HookManager:
    """No-op hook manager for tool execution lifecycle."""

    def before_tool_call(
        self, ctx: Context, tool_name: str, args: Dict[str, Any]
    ) -> None:
        """Run before a tool is invoked."""

    def after_tool_call(
        self,
        ctx: Context,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
    ) -> None:
        """Run after a tool is invoked."""
