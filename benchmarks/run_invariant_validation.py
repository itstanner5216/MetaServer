#!/usr/bin/env python3
"""
Run invariant validation and save results to text file.
"""

import sys
from datetime import datetime
from pathlib import Path

# Set up proper Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Now import from the project
from meta_mcp.registry.registry import ToolRegistry
from meta_mcp.retrieval.search import SemanticSearch


class InvariantValidator:
    """Validate system invariants."""

    def __init__(self):
        self.failures = []
        self.warnings = []
        self.checks = 0

    def check(self, condition: bool, message: str, critical: bool = True):
        """
        Check an invariant condition.

        Args:
            condition: Condition that must be True
            message: Description of the invariant
            critical: If True, failure is critical; if False, it's a warning
        """
        self.checks += 1

        if not condition:
            if critical:
                self.failures.append(message)
            else:
                self.warnings.append(message)

    def report(self) -> bool:
        """
        Print validation report.

        Returns:
            True if all critical checks passed
        """
        print("=" * 60)
        print("MetaMCP+ Invariant Validation")
        print("=" * 60)
        print()
        print(f"Total checks: {self.checks}")
        print(f"Failures: {len(self.failures)}")
        print(f"Warnings: {len(self.warnings)}")
        print()

        if self.failures:
            print("CRITICAL FAILURES:")
            for i, failure in enumerate(self.failures, 1):
                print(f"  {i}. {failure}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
            print()

        if not self.failures and not self.warnings:
            print("✅ All invariants validated successfully!")
            print()
            return True
        if not self.failures:
            print("⚠️  All critical checks passed, but warnings exist")
            print()
            return True
        print("❌ Critical invariant violations detected!")
        print()
        return False


def validate_registry_invariants(validator: InvariantValidator):
    """Validate tool registry invariants."""
    print("Validating registry invariants...")

    try:
        registry = ToolRegistry.from_yaml("config/tools.yaml")
    except Exception as e:
        validator.check(False, f"Failed to load registry: {e}")
        return

    tools = registry.get_all_summaries()

    # Check: At least one tool exists
    validator.check(len(tools) > 0, "Registry must contain at least one tool")

    # Check: All tool IDs are unique
    tool_ids = [tool.tool_id for tool in tools]
    validator.check(len(tool_ids) == len(set(tool_ids)), "All tool IDs must be unique")

    # Check: All tools have valid risk levels
    valid_risks = {"safe", "sensitive", "dangerous"}
    for tool in tools:
        validator.check(
            tool.risk_level in valid_risks,
            f"Tool {tool.tool_id} has invalid risk level: {tool.risk_level}",
        )

    # Check: All tools have non-empty descriptions
    for tool in tools:
        validator.check(
            len(tool.description_1line) > 0, f"Tool {tool.tool_id} has empty description_1line"
        )

    # Check: All tools have at least one tag
    for tool in tools:
        validator.check(len(tool.tags) > 0, f"Tool {tool.tool_id} has no tags")

    # Check: Bootstrap tools exist
    bootstrap_tools = registry.get_bootstrap_tools()
    validator.check("search_tools" in bootstrap_tools, "Bootstrap tool 'search_tools' must exist")
    validator.check(
        "get_tool_schema" in bootstrap_tools, "Bootstrap tool 'get_tool_schema' must exist"
    )


def validate_search_invariants(validator: InvariantValidator):
    """Validate semantic search invariants."""
    print("Validating search invariants...")

    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)

    # Check: Index builds successfully
    try:
        searcher._build_index()
        validator.check(True, "Embedding index built successfully")
    except Exception as e:
        validator.check(False, f"Failed to build embedding index: {e}")
        return

    # Check: Search returns results
    test_queries = ["read files", "write data", "network operations"]

    for query in test_queries:
        results = searcher.search(query, limit=5)
        validator.check(
            len(results) > 0, f"Search for '{query}' returned no results", critical=False
        )

    # Check: Results are ranked (descending scores)
    results = searcher.search("file operations", limit=10)
    if len(results) > 1:
        scores = [r.relevance_score for r in results]
        validator.check(
            scores == sorted(scores, reverse=True),
            "Search results must be ranked by descending relevance",
        )

    # Check: All scores in valid range [0, 1]
    for result in results:
        validator.check(
            0.0 <= result.relevance_score <= 1.0,
            f"Relevance score {result.relevance_score} out of range [0, 1]",
        )


def validate_embedding_invariants(validator: InvariantValidator):
    """Validate embedding invariants."""
    print("Validating embedding invariants...")

    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)
    searcher._build_index()

    tools = registry.get_all_summaries()

    # Check: All tools have embeddings
    for tool in tools:
        embedding = searcher.embedder.get_cached_embedding(tool.tool_id)
        validator.check(embedding is not None, f"Tool {tool.tool_id} has no embedding")

    # Check: Embeddings are normalized (unit length)
    for tool in tools:
        embedding = searcher.embedder.get_cached_embedding(tool.tool_id)
        if embedding:
            magnitude = sum(x * x for x in embedding) ** 0.5
            validator.check(
                abs(magnitude - 1.0) < 0.01,  # Allow small floating point error
                f"Tool {tool.tool_id} embedding not normalized (magnitude={magnitude:.3f})",
                critical=False,
            )

    # Check: Embedding dimension consistency
    if tools:
        first_embedding = searcher.embedder.get_cached_embedding(tools[0].tool_id)
        expected_dim = len(first_embedding) if first_embedding else 0

        for tool in tools[1:]:
            embedding = searcher.embedder.get_cached_embedding(tool.tool_id)
            if embedding:
                validator.check(
                    len(embedding) == expected_dim,
                    f"Tool {tool.tool_id} has inconsistent embedding dimension",
                )


def validate_security_properties(validator: InvariantValidator):
    """Validate security-related invariants."""
    print("Validating security properties...")

    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)

    # Check: Search results don't leak schemas
    results = searcher.search("operations", limit=10)

    for result in results:
        validator.check(
            not hasattr(result, "schema_min"),
            f"Search result for {result.tool_id} leaks schema_min",
        )
        validator.check(
            not hasattr(result, "schema_full"),
            f"Search result for {result.tool_id} leaks schema_full",
        )

    # Check: Dangerous tools are marked correctly
    tools = registry.get_all_summaries()
    dangerous_keywords = ["execute", "shell", "command", "admin"]

    for tool in tools:
        has_dangerous_keyword = any(
            kw in tool.tool_id.lower() or kw in tool.description_1line.lower()
            for kw in dangerous_keywords
        )

        if has_dangerous_keyword:
            validator.check(
                tool.risk_level in ["sensitive", "dangerous"],
                f"Tool {tool.tool_id} appears dangerous but has risk_level={tool.risk_level}",
                critical=False,
            )


def main():
    """Run all invariant validations."""
    validator = InvariantValidator()

    validate_registry_invariants(validator)
    validate_search_invariants(validator)
    validate_embedding_invariants(validator)
    validate_security_properties(validator)

    success = validator.report()

    # Save report to file
    output_path = project_root / "benchmarks" / "invariant_validation.txt"

    # Capture the report in text format
    with open(output_path, "w") as f:
        f.write("MetaMCP+ Invariant Validation Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Total checks: {validator.checks}\n")
        f.write(f"Failures: {len(validator.failures)}\n")
        f.write(f"Warnings: {len(validator.warnings)}\n\n")

        if validator.failures:
            f.write("CRITICAL FAILURES:\n")
            for i, failure in enumerate(validator.failures, 1):
                f.write(f"  {i}. {failure}\n")
            f.write("\n")

        if validator.warnings:
            f.write("WARNINGS:\n")
            for i, warning in enumerate(validator.warnings, 1):
                f.write(f"  {i}. {warning}\n")
            f.write("\n")

        if not validator.failures and not validator.warnings:
            f.write("✅ All invariants validated successfully!\n")
        elif not validator.failures:
            f.write("⚠️  All critical checks passed, but warnings exist\n")
        else:
            f.write("❌ Critical invariant violations detected!\n")

    print(f"\nReport saved to: {output_path}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
