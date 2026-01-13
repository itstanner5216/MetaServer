"""Tool invocation helpers."""

from typing import Any, Awaitable, Callable, Dict

from loguru import logger

from ..config import Config
from ..toon import encode_output


def _apply_toon_encoding(result: Any) -> Any:
    """
    Apply TOON encoding to tool result if enabled.

    Args:
        result: Tool execution result

    Returns:
        Encoded result if TOON enabled, otherwise unchanged result
    """
    if not Config.ENABLE_TOON_OUTPUTS:
        return result

    try:
        return encode_output(result, threshold=Config.TOON_ARRAY_THRESHOLD)
    except Exception as e:
        # Fail-safe: return original result if encoding fails
        logger.warning(f"TOON encoding failed: {e}, returning original result")
        return result


async def invoke_tool(
    ctx: Any,
    tool_name: str,
    args: Dict[str, Any],
    call_next: Callable[[], Awaitable[Any]],
) -> Any:
    """
    Invoke a tool via the next middleware and apply TOON encoding.

    Args:
        ctx: FastMCP context
        tool_name: Name of the tool being invoked
        args: Tool arguments
        call_next: Next middleware in chain

    Returns:
        Tool result with TOON encoding applied when enabled
    """
    _ = (ctx, tool_name, args)
    result = await call_next()
    return _apply_toon_encoding(result)
