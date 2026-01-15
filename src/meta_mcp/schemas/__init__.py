"""Progressive schema delivery for MetaMCP.

This package implements Phase 5 of the MetaMCP+ design, providing
progressive schema delivery to minimize token consumption.

Modules:
- minimizer: Reduces schemas to minimal form (15-50 tokens)
- expander: Restores full schemas on demand
"""

from .expander import expand_schema
from .minimizer import minimize_schema

__all__ = ["expand_schema", "minimize_schema"]
