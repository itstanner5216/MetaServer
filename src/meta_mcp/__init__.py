"""Meta MCP Server - FastMCP-based server infrastructure."""

from importlib import import_module

__version__ = "0.1.0"

_EXPORTS = {
    "Config": (".config", "Config"),
    "ExecutionMode": (".state", "ExecutionMode"),
    "governance_state": (".state", "governance_state"),
    "AuditEvent": (".audit", "AuditEvent"),
    "audit_logger": (".audit", "audit_logger"),
}

__all__ = [
    "AuditEvent",
    "Config",
    "ExecutionMode",
    "__version__",
    "audit_logger",
    "governance_state",
]


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr)
    globals()[name] = value
    return value
