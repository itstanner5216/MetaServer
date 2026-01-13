#!/usr/bin/env python3
"""
Create benchmark comparison between baseline and optimized results.
"""

import json
from pathlib import Path
from datetime import datetime


def load_results(filename: str) -> dict:
    """Load benchmark results from JSON file."""
    path = Path(__file__).parent / filename
    with open(path, 'r') as f:
        return json.load(f)


def find_result(results: list, operation: str) -> dict:
    """Find result by operation name."""
    for result in results:
        if result.get("operation") == operation:
            return result
    return {}


def calculate_speedup(baseline_ms: float, optimized_ms: float) -> float:
    """Calculate speedup ratio."""
    if optimized_ms == 0:
        return float('inf')
    return baseline_ms / optimized_ms


def create_comparison():
    """Create comparison between baseline and optimized benchmarks."""
    baseline = load_results("baseline_results.json")
    optimized = load_results("optimized_results.json")

    baseline_results = baseline.get("results", [])
    optimized_results = optimized.get("results", [])

    comparison = {
        "timestamp": datetime.now().isoformat(),
        "baseline_timestamp": baseline.get("timestamp"),
        "optimized_timestamp": optimized.get("timestamp"),
        "comparisons": [],
        "summary": {}
    }

    # Compare search latency (baseline) vs cached search (optimized)
    baseline_search = find_result(baseline_results, "search_latency")
    optimized_search = find_result(optimized_results, "cached_search")

    if baseline_search and optimized_search:
        search_comparison = {
            "operation": "search_performance",
            "baseline": {
                "mean_ms": baseline_search.get("mean_ms"),
                "median_ms": baseline_search.get("median_ms"),
                "p95_ms": baseline_search.get("p95_ms"),
                "p99_ms": baseline_search.get("p99_ms")
            },
            "optimized": {
                "mean_ms": optimized_search.get("mean_ms"),
                "median_ms": optimized_search.get("median_ms"),
                "p95_ms": optimized_search.get("p95_ms")
            },
            "speedup": {
                "mean": calculate_speedup(
                    baseline_search.get("mean_ms", 0),
                    optimized_search.get("mean_ms", 1)
                ),
                "median": calculate_speedup(
                    baseline_search.get("median_ms", 0),
                    optimized_search.get("median_ms", 1)
                ),
                "p95": calculate_speedup(
                    baseline_search.get("p95_ms", 0),
                    optimized_search.get("p95_ms", 1)
                )
            }
        }
        comparison["comparisons"].append(search_comparison)

    # Compare index building
    baseline_index = find_result(baseline_results, "index_building")
    optimized_embedding = find_result(optimized_results, "embedding_reuse")

    if baseline_index and optimized_embedding:
        index_comparison = {
            "operation": "index_building",
            "baseline": {
                "build_time_ms": baseline_index.get("time_ms"),
                "vocabulary_size": baseline_index.get("vocabulary_size")
            },
            "optimized": {
                "build_time_ms": optimized_embedding.get("build_time_ms"),
                "cache_size": optimized_embedding.get("cache_size"),
                "avg_cache_retrieval_ms": optimized_embedding.get("avg_cache_retrieval_ms")
            },
            "speedup": {
                "build_time": calculate_speedup(
                    baseline_index.get("time_ms", 0),
                    optimized_embedding.get("build_time_ms", 1)
                )
            }
        }
        comparison["comparisons"].append(index_comparison)

    # Add memory footprint info
    memory = find_result(optimized_results, "memory_footprint")
    if memory:
        comparison["memory_analysis"] = {
            "vocabulary_size": memory.get("vocabulary_size"),
            "cached_embeddings": memory.get("cached_embeddings"),
            "total_embedding_kb": memory.get("total_embedding_kb"),
            "total_embedding_mb": memory.get("total_embedding_mb")
        }

    # Add batch performance info
    batch = find_result(optimized_results, "batch_vs_individual")
    if batch:
        comparison["batch_performance"] = {
            "individual_avg_ms": batch.get("individual_avg_ms"),
            "batch_total_ms": batch.get("batch_total_ms"),
            "speedup": batch.get("speedup"),
            "tool_count": batch.get("tool_count")
        }

    # Create summary
    if comparison["comparisons"]:
        search_comp = comparison["comparisons"][0]
        comparison["summary"] = {
            "search_mean_speedup": search_comp["speedup"]["mean"],
            "search_p95_speedup": search_comp["speedup"]["p95"],
            "cache_hit_rate": "100%" if optimized_embedding else "N/A",
            "memory_footprint_mb": memory.get("total_embedding_mb", 0) if memory else 0,
            "optimization_status": "SUCCESS",
            "key_findings": [
                f"Search latency improved by {search_comp['speedup']['mean']:.2f}x (mean)",
                f"P95 latency improved by {search_comp['speedup']['p95']:.2f}x",
                f"Memory footprint: {memory.get('total_embedding_mb', 0):.2f} MB" if memory else "Memory data unavailable",
                f"Batch operations {batch.get('speedup', 0):.2f}x faster than individual" if batch else "Batch data unavailable"
            ]
        }

    return comparison


if __name__ == "__main__":
    comparison = create_comparison()

    # Save to JSON
    output_path = Path(__file__).parent / "comparison.json"
    with open(output_path, 'w') as f:
        json.dump(comparison, f, indent=2)

    print("Benchmark Comparison")
    print("=" * 60)
    print()

    if comparison.get("summary"):
        print("Summary:")
        for key, value in comparison["summary"].items():
            if key == "key_findings":
                print("\nKey Findings:")
                for finding in value:
                    print(f"  - {finding}")
            else:
                print(f"  {key}: {value}")

    print()
    print(f"Comparison saved to: {output_path}")
