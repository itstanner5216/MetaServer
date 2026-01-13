#!/usr/bin/env python3
"""
Run optimized benchmarks and save results to JSON.
"""

import json
import sys
import time
import statistics
from datetime import datetime
from pathlib import Path

# Set up proper Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Now import from the project
from meta_mcp.registry.registry import ToolRegistry
from meta_mcp.retrieval.search import SemanticSearch


def benchmark_cached_searches(iterations: int = 100) -> dict:
    """Benchmark search with hot cache."""
    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)

    # Build index once
    searcher._build_index()

    # Use same query to test cache
    query = "read files from disk"

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        results = searcher.search(query, limit=10)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "operation": "cached_search",
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "p95_ms": statistics.quantiles(times, n=20)[18],
        "min_ms": min(times),
        "max_ms": max(times),
        "iterations": iterations
    }


def benchmark_embedding_reuse() -> dict:
    """Benchmark embedding cache hit rate."""
    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)

    # Build index (populates cache)
    start_build = time.perf_counter()
    searcher._build_index()
    build_time = time.perf_counter() - start_build

    # Count cached embeddings
    cache_size = len(searcher.embedder._cache)

    # Measure cache retrieval time
    tools = registry.get_all_summaries()
    times = []

    for tool in tools:
        start = time.perf_counter()
        embedding = searcher.embedder.get_cached_embedding(tool.tool_id)
        elapsed = time.perf_counter() - start
        if embedding:
            times.append(elapsed * 1000)

    return {
        "operation": "embedding_reuse",
        "cache_size": cache_size,
        "build_time_ms": build_time * 1000,
        "avg_cache_retrieval_ms": statistics.mean(times) if times else 0,
        "cache_hits": len(times)
    }


def benchmark_batch_vs_individual() -> dict:
    """Compare batch operations vs individual operations."""
    registry = ToolRegistry.from_yaml("config/tools.yaml")
    tools = registry.get_all_summaries()

    if len(tools) < 5:
        return {"operation": "batch_vs_individual", "error": "Not enough tools"}

    sample_tools = tools[:5]

    # Individual retrievals
    individual_times = []
    for tool in sample_tools:
        start = time.perf_counter()
        _ = registry.get(tool.tool_id)
        elapsed = time.perf_counter() - start
        individual_times.append(elapsed * 1000)

    # Batch retrieval (simulated)
    start = time.perf_counter()
    batch_results = [registry.get(tool.tool_id) for tool in sample_tools]
    batch_time = time.perf_counter() - start

    return {
        "operation": "batch_vs_individual",
        "individual_total_ms": sum(individual_times),
        "individual_avg_ms": statistics.mean(individual_times),
        "batch_total_ms": batch_time * 1000,
        "speedup": sum(individual_times) / (batch_time * 1000),
        "tool_count": len(sample_tools)
    }


def benchmark_memory_footprint() -> dict:
    """Estimate memory footprint of embeddings and cache."""
    import sys

    registry = ToolRegistry.from_yaml("config/tools.yaml")
    searcher = SemanticSearch(registry)
    searcher._build_index()

    # Estimate embedding size
    if searcher.embedder._vocabulary:
        vocab_size = len(searcher.embedder._vocabulary)
        cache_size = len(searcher.embedder._cache)

        # Rough estimate: each float is 8 bytes, plus overhead
        bytes_per_embedding = vocab_size * 8
        total_embedding_bytes = bytes_per_embedding * cache_size

        return {
            "operation": "memory_footprint",
            "vocabulary_size": vocab_size,
            "cached_embeddings": cache_size,
            "bytes_per_embedding": bytes_per_embedding,
            "total_embedding_kb": total_embedding_bytes / 1024,
            "total_embedding_mb": total_embedding_bytes / (1024 * 1024)
        }

    return {"operation": "memory_footprint", "error": "No embeddings generated"}


def run_optimized_benchmarks():
    """Run all optimized benchmarks."""
    print("=" * 60)
    print("MetaMCP+ Optimized Performance Benchmarks")
    print("=" * 60)
    print()

    benchmarks = [
        benchmark_embedding_reuse,
        lambda: benchmark_cached_searches(iterations=100),
        benchmark_batch_vs_individual,
        benchmark_memory_footprint
    ]

    results = []
    for bench in benchmarks:
        print(f"Running {bench.__name__ if hasattr(bench, '__name__') else 'benchmark'}...", end=" ")
        sys.stdout.flush()

        try:
            result = bench()
            results.append(result)
            print("DONE")
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({"operation": "unknown", "error": str(e)})

    print()
    print("=" * 60)
    print("Results")
    print("=" * 60)

    for result in results:
        print()
        print(f"Operation: {result['operation']}")

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        for key, value in result.items():
            if key == "operation":
                continue

            if isinstance(value, float):
                print(f"  {key}: {value:.3f}")
            else:
                print(f"  {key}: {value}")

    print()
    print("=" * 60)

    return results


if __name__ == "__main__":
    try:
        print("Running optimized benchmarks...")
        results = run_optimized_benchmarks()

        # Add timestamp
        output = {
            "timestamp": datetime.now().isoformat(),
            "benchmark_type": "optimized",
            "results": results
        }

        # Save to JSON
        output_path = project_root / "benchmarks" / "optimized_results.json"
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\nResults saved to: {output_path}")

    except Exception as e:
        print(f"Error running benchmarks: {e}")
        import traceback
        traceback.print_exc()

        # Save error to JSON
        error_output = {
            "timestamp": datetime.now().isoformat(),
            "benchmark_type": "optimized",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

        output_path = project_root / "benchmarks" / "optimized_results.json"
        with open(output_path, 'w') as f:
            json.dump(error_output, f, indent=2)

        sys.exit(1)
