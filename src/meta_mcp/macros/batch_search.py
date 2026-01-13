"""
Batch search operations for tools.

Provides efficient batch search across multiple queries.
"""

from typing import Dict, List, Optional
from ..registry.models import ToolCandidate
from ..registry.registry import ToolRegistry


def batch_search_tools(
    registry: ToolRegistry,
    queries: Optional[List[str]],
    limit: int = 10,
    min_score: float = 0.0,
    exclude_risk_levels: Optional[List[str]] = None
) -> Dict[str, List[ToolCandidate]]:
    """
    Perform multiple search queries in a single batch operation.

    Args:
        registry: Tool registry instance
        queries: List of search query strings
        limit: Maximum number of results per query
        min_score: Minimum relevance score threshold
        exclude_risk_levels: Risk levels to exclude from results

    Returns:
        Dictionary mapping query -> list of ToolCandidate objects
    """
    if queries is None or len(queries) == 0:
        return {}

    results = {}

    for query in queries:
        # Perform search
        candidates = registry.search(query)

        # Apply limit
        candidates = candidates[:limit]

        # Apply min score filter
        if min_score > 0:
            candidates = [c for c in candidates if c.relevance_score >= min_score]

        # Apply risk level filter
        if exclude_risk_levels:
            candidates = [
                c for c in candidates
                if c.risk_level not in exclude_risk_levels
            ]

        results[query] = candidates

    return results
