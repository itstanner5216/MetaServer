"""Hook manager for tool execution lifecycle."""

from typing import Any, Dict

from fastmcp import Context


class HookManager:
    """Provide pre/post hooks around tool execution.

    Default implementations are no-ops and must not mutate arguments or results.
    """

    def before_tool_call(
        self, ctx: Context, tool_name: str, args: Dict[str, Any]
    ) -> None:
        """Called before a tool is executed."""

    def after_tool_call(
        self, ctx: Context, tool_name: str, args: Dict[str, Any], result: Any
    ) -> None:
        """Called after a tool is executed."""


hook_manager = HookManager()
