"""Tool invocation helpers."""

from typing import Any, Awaitable, Callable, Dict

from fastmcp import Context


async def invoke_tool(
    ctx: Context,
    tool_name: str,
    args: Dict[str, Any],
    call_next: Callable[[], Awaitable[Any]],
) -> Any:
    """
    Invoke the next tool handler and apply TOON encoding.

    Args:
        ctx: Current request context.
        tool_name: Name of the tool being invoked.
        args: Tool arguments.
        call_next: Callable to execute the next middleware/tool.

    Returns:
        Tool response with TOON encoding applied when enabled.
    """
    _ = (ctx, tool_name, args)
    result = await call_next()
    from ..middleware import GovernanceMiddleware

    return GovernanceMiddleware._apply_toon_encoding(result)
