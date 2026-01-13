#!/usr/bin/env python3
"""
Run baseline benchmarks and save results to JSON.
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
from meta_mcp.registry.registry import ToolRegistry, DEFAULT_TOOLS_YAML_PATH
from meta_mcp.retrieval.search import SemanticSearch


def benchmark_registry_loading() -> dict:
    """Benchmark registry loading time."""
    start = time.perf_counter()
    registry = ToolRegistry.from_yaml(DEFAULT_TOOLS_YAML_PATH)
    elapsed = time.perf_counter() - start

    return {
        "operation": "registry_loading",
        "time_ms": elapsed * 1000,
        "tool_count": len(registry.get_all_summaries())
    }


def benchmark_search_latency(iterations: int = 100) -> dict:
    """Benchmark search operation latency."""
    registry = ToolRegistry.from_yaml(DEFAULT_TOOLS_YAML_PATH)
    searcher = SemanticSearch(registry)

    # Warm up
    searcher.search("read files")

    # Benchmark queries
    queries = [
        "read files from disk",
        "write data to storage",
        "network operations",
        "send email messages",
        "list directory contents"
    ]

    times = []
    for _ in range(iterations):
        for query in queries:
            start = time.perf_counter()
            results = searcher.search(query, limit=10)
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)

    return {
        "operation": "search_latency",
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "p95_ms": statistics.quantiles(times, n=20)[18],  # 95th percentile
        "p99_ms": statistics.quantiles(times, n=100)[98],  # 99th percentile
        "min_ms": min(times),
        "max_ms": max(times),
        "iterations": len(times)
    }


def benchmark_index_building() -> dict:
    """Benchmark embedding index building time."""
    registry = ToolRegistry.from_yaml(DEFAULT_TOOLS_YAML_PATH)
    searcher = SemanticSearch(registry)

    start = time.perf_counter()
    searcher._build_index()
    elapsed = time.perf_counter() - start

    return {
        "operation": "index_building",
        "time_ms": elapsed * 1000,
        "vocabulary_size": len(searcher.embedder._vocabulary)
    }


def benchmark_tool_retrieval(iterations: int = 1000) -> dict:
    """Benchmark individual tool retrieval."""
    registry = ToolRegistry.from_yaml(DEFAULT_TOOLS_YAML_PATH)

    # Get a sample tool ID
    tools = registry.get_all_summaries()
    if not tools:
        return {"operation": "tool_retrieval", "error": "No tools found"}

    tool_id = tools[0].tool_id

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        tool = registry.get(tool_id)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "operation": "tool_retrieval",
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "iterations": iterations
    }


def run_baseline_benchmarks():
    """Run all baseline benchmarks."""
    print("=" * 60)
    print("MetaMCP+ Baseline Performance Benchmarks")
    print("=" * 60)
    print()

    benchmarks = [
        benchmark_registry_loading,
        benchmark_index_building,
        lambda: benchmark_search_latency(iterations=20),
        lambda: benchmark_tool_retrieval(iterations=1000)
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
        print("Running baseline benchmarks...")
        results = run_baseline_benchmarks()

        # Add timestamp
        output = {
            "timestamp": datetime.now().isoformat(),
            "benchmark_type": "baseline",
            "results": results
        }

        # Save to JSON
        output_path = project_root / "benchmarks" / "baseline_results.json"
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
            "benchmark_type": "baseline",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

        output_path = project_root / "benchmarks" / "baseline_results.json"
        with open(output_path, 'w') as f:
            json.dump(error_output, f, indent=2)

        sys.exit(1)
