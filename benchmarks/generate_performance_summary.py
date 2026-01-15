#!/usr/bin/env python3
"""
Generate human-readable performance summary report.
"""

import json
from datetime import datetime
from pathlib import Path


def load_json(filename: str) -> dict:
    """Load JSON file."""
    path = Path(__file__).parent / filename
    with open(path) as f:
        return json.load(f)


def find_result(results: list, operation: str) -> dict:
    """Find result by operation name."""
    for result in results:
        if result.get("operation") == operation:
            return result
    return {}


def format_ms(ms: float) -> str:
    """Format milliseconds with appropriate precision."""
    if ms < 0.001:
        return f"{ms * 1000:.3f} µs"
    if ms < 1:
        return f"{ms:.3f} ms"
    return f"{ms:.2f} ms"


def generate_summary():
    """Generate performance summary report."""
    baseline = load_json("baseline_results.json")
    optimized = load_json("optimized_results.json")
    comparison = load_json("comparison.json")

    baseline_results = baseline.get("results", [])
    optimized_results = optimized.get("results", [])

    lines = []
    lines.append("=" * 70)
    lines.append("MetaMCP+ Performance Summary Report")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Baseline run: {baseline.get('timestamp', 'N/A')}")
    lines.append(f"Optimized run: {optimized.get('timestamp', 'N/A')}")
    lines.append("")

    # Executive Summary
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 70)
    summary = comparison.get("summary", {})
    if summary:
        lines.append(f"Overall Status: {summary.get('optimization_status', 'N/A')}")
        lines.append(
            f"Search Performance Improvement: {summary.get('search_mean_speedup', 0):.2f}x"
        )
        lines.append(f"P95 Latency Improvement: {summary.get('search_p95_speedup', 0):.2f}x")
        lines.append(f"Cache Hit Rate: {summary.get('cache_hit_rate', 'N/A')}")
        lines.append(f"Memory Footprint: {summary.get('memory_footprint_mb', 0):.2f} MB")
    lines.append("")

    # Key Metrics Table
    lines.append("KEY METRICS")
    lines.append("-" * 70)
    lines.append("")

    # Registry Loading
    registry_baseline = find_result(baseline_results, "registry_loading")
    if registry_baseline:
        lines.append("1. Registry Loading")
        lines.append(f"   Time: {format_ms(registry_baseline.get('time_ms', 0))}")
        lines.append(f"   Tool Count: {registry_baseline.get('tool_count', 0)}")
        lines.append("")

    # Search Latency
    search_baseline = find_result(baseline_results, "search_latency")
    search_optimized = find_result(optimized_results, "cached_search")

    lines.append("2. Search Performance (Baseline vs Optimized)")
    lines.append("")
    lines.append("   Metric          Baseline        Optimized       Improvement")
    lines.append("   " + "-" * 62)

    if search_baseline and search_optimized:
        mean_base = search_baseline.get("mean_ms", 0)
        mean_opt = search_optimized.get("mean_ms", 0)
        mean_speedup = mean_base / mean_opt if mean_opt > 0 else 0

        median_base = search_baseline.get("median_ms", 0)
        median_opt = search_optimized.get("median_ms", 0)
        median_speedup = median_base / median_opt if median_opt > 0 else 0

        p95_base = search_baseline.get("p95_ms", 0)
        p95_opt = search_optimized.get("p95_ms", 0)
        p95_speedup = p95_base / p95_opt if p95_opt > 0 else 0

        p99_base = search_baseline.get("p99_ms", 0)

        lines.append(
            f"   Mean            {format_ms(mean_base):15s} {format_ms(mean_opt):15s} {mean_speedup:.2f}x"
        )
        lines.append(
            f"   Median          {format_ms(median_base):15s} {format_ms(median_opt):15s} {median_speedup:.2f}x"
        )
        lines.append(
            f"   P95             {format_ms(p95_base):15s} {format_ms(p95_opt):15s} {p95_speedup:.2f}x"
        )
        lines.append(f"   P99             {format_ms(p99_base):15s} {'N/A':15s} N/A")
    lines.append("")

    # Index Building
    index_baseline = find_result(baseline_results, "index_building")
    embedding_opt = find_result(optimized_results, "embedding_reuse")

    lines.append("3. Index Building & Embedding Cache")
    if index_baseline:
        lines.append(f"   Build Time: {format_ms(index_baseline.get('time_ms', 0))}")
        lines.append(f"   Vocabulary Size: {index_baseline.get('vocabulary_size', 0)}")
    if embedding_opt:
        lines.append(f"   Cache Size: {embedding_opt.get('cache_size', 0)} embeddings")
        lines.append(f"   Cache Hits: {embedding_opt.get('cache_hits', 0)}")
        lines.append(
            f"   Avg Cache Retrieval: {format_ms(embedding_opt.get('avg_cache_retrieval_ms', 0))}"
        )
    lines.append("")

    # Tool Retrieval
    tool_retrieval = find_result(baseline_results, "tool_retrieval")
    if tool_retrieval:
        lines.append("4. Tool Retrieval Performance")
        lines.append(f"   Mean: {format_ms(tool_retrieval.get('mean_ms', 0))}")
        lines.append(f"   Median: {format_ms(tool_retrieval.get('median_ms', 0))}")
        lines.append(f"   Iterations: {tool_retrieval.get('iterations', 0)}")
        lines.append("")

    # Memory Footprint
    memory = find_result(optimized_results, "memory_footprint")
    if memory:
        lines.append("MEMORY ANALYSIS")
        lines.append("-" * 70)
        lines.append(f"Vocabulary Size: {memory.get('vocabulary_size', 0)} terms")
        lines.append(f"Cached Embeddings: {memory.get('cached_embeddings', 0)}")
        lines.append(f"Bytes per Embedding: {memory.get('bytes_per_embedding', 0)}")
        lines.append(f"Total Embedding Cache: {memory.get('total_embedding_kb', 0):.2f} KB")
        lines.append(f"Total Embedding Cache: {memory.get('total_embedding_mb', 0):.3f} MB")
        lines.append("")

    # Cache Hit Rates
    lines.append("CACHE PERFORMANCE")
    lines.append("-" * 70)
    if embedding_opt:
        cache_size = embedding_opt.get("cache_size", 0)
        cache_hits = embedding_opt.get("cache_hits", 0)
        hit_rate = (cache_hits / cache_size * 100) if cache_size > 0 else 0
        lines.append(f"Embedding Cache Hit Rate: {hit_rate:.1f}%")
        lines.append(
            f"Cache Retrieval Time: {format_ms(embedding_opt.get('avg_cache_retrieval_ms', 0))}"
        )
    lines.append("")

    # Batch Operations
    batch = find_result(optimized_results, "batch_vs_individual")
    if batch:
        lines.append("BATCH OPERATIONS")
        lines.append("-" * 70)
        lines.append(f"Individual Operations (avg): {format_ms(batch.get('individual_avg_ms', 0))}")
        lines.append(f"Batch Operations (total): {format_ms(batch.get('batch_total_ms', 0))}")
        lines.append(f"Speedup: {batch.get('speedup', 0):.2f}x")
        lines.append(f"Tool Count: {batch.get('tool_count', 0)}")
        lines.append("")

    # Optimization Gains
    lines.append("OPTIMIZATION GAINS")
    lines.append("-" * 70)
    if summary and summary.get("key_findings"):
        for finding in summary["key_findings"]:
            lines.append(f"  • {finding}")
    lines.append("")

    # Performance Bottlenecks
    lines.append("PERFORMANCE BOTTLENECKS IDENTIFIED")
    lines.append("-" * 70)
    bottlenecks = []

    if search_baseline:
        p99 = search_baseline.get("p99_ms", 0)
        mean = search_baseline.get("mean_ms", 0)
        if p99 > mean * 2:
            bottlenecks.append(
                f"Search P99 latency ({format_ms(p99)}) is {p99 / mean:.1f}x higher than mean"
            )

    if registry_baseline:
        reg_time = registry_baseline.get("time_ms", 0)
        if reg_time > 5:
            bottlenecks.append(f"Registry loading time ({format_ms(reg_time)}) could be optimized")

    if not bottlenecks:
        lines.append("  • No significant bottlenecks detected")
    else:
        for bottleneck in bottlenecks:
            lines.append(f"  • {bottleneck}")
    lines.append("")

    # Recommendations
    lines.append("RECOMMENDATIONS")
    lines.append("-" * 70)
    recommendations = []

    if memory and memory.get("total_embedding_mb", 0) < 1:
        recommendations.append("Memory footprint is excellent (<1 MB)")

    if search_optimized and search_optimized.get("mean_ms", 0) < 0.2:
        recommendations.append("Search latency is excellent (<0.2ms)")

    if batch and batch.get("speedup", 0) > 2:
        recommendations.append("Continue using batch operations where possible")

    if not recommendations:
        recommendations.append("System performance is optimal")
    else:
        for rec in recommendations:
            lines.append(f"  • {rec}")
    lines.append("")

    lines.append("=" * 70)
    lines.append("End of Report")
    lines.append("=" * 70)

    return "\n".join(lines)


if __name__ == "__main__":
    summary = generate_summary()

    # Save to file
    output_path = Path(__file__).parent / "PERFORMANCE_SUMMARY.txt"
    with open(output_path, "w") as f:
        f.write(summary)

    # Print to console
    print(summary)
    print()
    print(f"Summary saved to: {output_path}")
