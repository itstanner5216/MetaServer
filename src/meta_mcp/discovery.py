"""
Discovery utilities and legacy compatibility shims.

Module Status:
- format_search_results(): MOVED to meta_mcp.registry.formatting
- ToolRegistry/tool_registry: DEPRECATED - use meta_mcp.registry.tool_registry

Source of truth:
- Tool definitions are loaded from config/tools.yaml via meta_mcp.registry.

Migration Path:
- OLD: from meta_mcp.discovery import tool_registry
- NEW: from meta_mcp.registry import tool_registry
"""

from warnings import warn

from .registry import tool_registry as _canonical_tool_registry


class ToolRegistry:
    """
    Deprecated ToolRegistry shim.

    The canonical registry is loaded from config/tools.yaml. Use
    meta_mcp.registry.ToolRegistry or meta_mcp.registry.tool_registry.
    """

    def __init__(self, *args, **kwargs):
        warn(
            "meta_mcp.discovery.ToolRegistry is deprecated; use "
            "meta_mcp.registry.ToolRegistry loaded from config/tools.yaml.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._registry = _canonical_tool_registry

    def __getattr__(self, name):
        warn(
            "meta_mcp.discovery.ToolRegistry is deprecated; use "
            "meta_mcp.registry.ToolRegistry loaded from config/tools.yaml.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self._registry, name)


class _DeprecatedToolRegistryProxy:
    def __init__(self, registry):
        self._registry = registry

    def __getattr__(self, name):
        warn(
            "meta_mcp.discovery.tool_registry is deprecated; use "
            "meta_mcp.registry.tool_registry loaded from config/tools.yaml.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self._registry, name)


# Deprecated module-level singleton proxy.
tool_registry = _DeprecatedToolRegistryProxy(_canonical_tool_registry)
