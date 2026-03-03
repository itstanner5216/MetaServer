"""Governance package exports with lazy imports to avoid circular dependencies."""

from importlib import import_module

_EXPORTS = {
    "ApprovalArtifactGenerator": (".artifacts", "ApprovalArtifactGenerator"),
    "ApprovalDecision": (".approval", "ApprovalDecision"),
    "ApprovalProvider": (".approval", "ApprovalProvider"),
    "ApprovalRequest": (".approval", "ApprovalRequest"),
    "ApprovalResponse": (".approval", "ApprovalResponse"),
    "ArtifactGenerationError": (".artifacts", "ArtifactGenerationError"),
    "DBusGUIProvider": (".approval", "DBusGUIProvider"),
    "FastMCPElicitProvider": (".approval", "FastMCPElicitProvider"),
    "PolicyDecision": (".policy", "PolicyDecision"),
    "SystemdFallbackProvider": (".approval", "SystemdFallbackProvider"),
    "decode_token": (".tokens", "decode_token"),
    "evaluate_policy": (".policy", "evaluate_policy"),
    "generate_token": (".tokens", "generate_token"),
    "get_approval_provider": (".approval", "get_approval_provider"),
    "get_artifact_generator": (".artifacts", "get_artifact_generator"),
    "verify_token": (".tokens", "verify_token"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr)
    globals()[name] = value
    return value
