"""Execution modes for governance policies."""

from enum import Enum


class ExecutionMode(str, Enum):
    """Tri-state execution mode for governance."""

    READ_ONLY = "read_only"
    PERMISSION = "permission"
    BYPASS = "bypass"
