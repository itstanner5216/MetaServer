#!/usr/bin/env python3
"""
Run load tests on MetaMCP+ system.

Tests:
- Concurrent search queries
- Concurrent tool retrieval
- Batch operations under load
"""

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

# Set up proper Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Now import from the project
from meta_mcp.registry.registry import ToolRegistry
from meta_mcp.retrieval.search import SemanticSearch


class LoadTester:
    """Run load tests on the system."""

    def __init__(self):
        self.registry = ToolRegistry.from_yaml("config/tools.yaml")
        self.searcher = SemanticSearch(self.registry)
        self.searcher._build_index()
        self.tools = self.registry.get_all_summaries()
        self.lock = Lock()
        self.errors = []

    def concurrent_search_test(self, num_threads: int = 10, queries_per_thread: int = 50) -> dict:
        """Test concurrent search queries."""
        print(
            f"Running concurrent search test ({num_threads} threads, {queries_per_thread} queries each)..."
        )

        queries = [
            "read files from disk",
            "write data to storage",
            "network operations",
            "send email messages",
            "list directory contents",
            "database queries",
            "authentication",
            "file operations",
            "data processing",
            "configuration management",
        ]

        def search_worker(thread_id: int) -> list:
            """Worker function for search."""
            times = []
            for i in range(queries_per_thread):
                query = queries[i % len(queries)]
                try:
                    start = time.perf_counter()
                    results = self.searcher.search(query, limit=5)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed * 1000)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Thread {thread_id}: {e!s}")
            return times

        all_times = []
        start_total = time.perf_counter()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(search_worker, i) for i in range(num_threads)]

            for future in as_completed(futures):
                try:
                    times = future.result()
                    all_times.extend(times)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Future error: {e!s}")

        total_time = time.perf_counter() - start_total

        if all_times:
            return {
                "test": "concurrent_search",
                "threads": num_threads,
                "queries_per_thread": queries_per_thread,
                "total_queries": len(all_times),
                "total_time_s": total_time,
                "throughput_qps": len(all_times) / total_time,
                "mean_latency_ms": statistics.mean(all_times),
                "median_latency_ms": statistics.median(all_times),
                "p95_latency_ms": statistics.quantiles(all_times, n=20)[18]
                if len(all_times) > 20
                else max(all_times),
                "min_latency_ms": min(all_times),
                "max_latency_ms": max(all_times),
                "errors": len(self.errors),
            }
        return {
            "test": "concurrent_search",
            "error": "No successful queries",
            "errors": self.errors,
        }

    def concurrent_retrieval_test(
        self, num_threads: int = 10, retrievals_per_thread: int = 100
    ) -> dict:
        """Test concurrent tool retrieval."""
        print(
            f"Running concurrent retrieval test ({num_threads} threads, {retrievals_per_thread} retrievals each)..."
        )

        if not self.tools:
            return {"test": "concurrent_retrieval", "error": "No tools available"}

        tool_ids = [tool.tool_id for tool in self.tools]

        def retrieval_worker(thread_id: int) -> list:
            """Worker function for retrieval."""
            times = []
            for i in range(retrievals_per_thread):
                tool_id = tool_ids[i % len(tool_ids)]
                try:
                    start = time.perf_counter()
                    tool = self.registry.get(tool_id)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed * 1000)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Thread {thread_id}: {e!s}")
            return times

        all_times = []
        start_total = time.perf_counter()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(retrieval_worker, i) for i in range(num_threads)]

            for future in as_completed(futures):
                try:
                    times = future.result()
                    all_times.extend(times)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Future error: {e!s}")

        total_time = time.perf_counter() - start_total

        if all_times:
            return {
                "test": "concurrent_retrieval",
                "threads": num_threads,
                "retrievals_per_thread": retrievals_per_thread,
                "total_retrievals": len(all_times),
                "total_time_s": total_time,
                "throughput_ops": len(all_times) / total_time,
                "mean_latency_ms": statistics.mean(all_times),
                "median_latency_ms": statistics.median(all_times),
                "p95_latency_ms": statistics.quantiles(all_times, n=20)[18]
                if len(all_times) > 20
                else max(all_times),
                "min_latency_ms": min(all_times),
                "max_latency_ms": max(all_times),
                "errors": len(self.errors),
            }
        return {
            "test": "concurrent_retrieval",
            "error": "No successful retrievals",
            "errors": self.errors,
        }

    def batch_stress_test(self, batch_sizes: list = None) -> dict:
        """Test batch operations under various loads."""
        print("Running batch stress test...")

        if batch_sizes is None:
            batch_sizes = [5, 10, 15]

        if not self.tools:
            return {"test": "batch_stress", "error": "No tools available"}

        results = []

        for batch_size in batch_sizes:
            batch_size = min(batch_size, len(self.tools))

            sample_tools = self.tools[:batch_size]
            iterations = 100

            times = []
            for _ in range(iterations):
                try:
                    start = time.perf_counter()
                    batch_results = [self.registry.get(tool.tool_id) for tool in sample_tools]
                    elapsed = time.perf_counter() - start
                    times.append(elapsed * 1000)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Batch size {batch_size}: {e!s}")

            if times:
                results.append(
                    {
                        "batch_size": batch_size,
                        "iterations": iterations,
                        "mean_time_ms": statistics.mean(times),
                        "median_time_ms": statistics.median(times),
                        "throughput_batches_per_sec": iterations / (sum(times) / 1000),
                        "avg_time_per_item_ms": statistics.mean(times) / batch_size,
                    }
                )

        return {"test": "batch_stress", "batch_results": results, "errors": len(self.errors)}

    def mixed_workload_test(self, duration_seconds: int = 5) -> dict:
        """Test mixed workload (searches and retrievals)."""
        print(f"Running mixed workload test ({duration_seconds}s)...")

        queries = ["read files", "write data", "network operations"]

        tool_ids = [tool.tool_id for tool in self.tools] if self.tools else []

        search_times = []
        retrieval_times = []
        operations = 0

        start_time = time.perf_counter()
        end_time = start_time + duration_seconds

        while time.perf_counter() < end_time:
            # Alternate between search and retrieval
            if operations % 2 == 0:
                # Search
                query = queries[operations % len(queries)]
                try:
                    start = time.perf_counter()
                    results = self.searcher.search(query, limit=5)
                    elapsed = time.perf_counter() - start
                    search_times.append(elapsed * 1000)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Search: {e!s}")
            # Retrieval
            elif tool_ids:
                tool_id = tool_ids[operations % len(tool_ids)]
                try:
                    start = time.perf_counter()
                    tool = self.registry.get(tool_id)
                    elapsed = time.perf_counter() - start
                    retrieval_times.append(elapsed * 1000)
                except Exception as e:
                    with self.lock:
                        self.errors.append(f"Retrieval: {e!s}")

            operations += 1

        total_time = time.perf_counter() - start_time

        return {
            "test": "mixed_workload",
            "duration_s": total_time,
            "total_operations": operations,
            "search_operations": len(search_times),
            "retrieval_operations": len(retrieval_times),
            "throughput_ops": operations / total_time,
            "search_mean_ms": statistics.mean(search_times) if search_times else 0,
            "retrieval_mean_ms": statistics.mean(retrieval_times) if retrieval_times else 0,
            "errors": len(self.errors),
        }


def run_load_tests():
    """Run all load tests."""
    print("=" * 60)
    print("MetaMCP+ Load Tests")
    print("=" * 60)
    print()

    tester = LoadTester()

    results = {"timestamp": datetime.now().isoformat(), "tests": []}

    # Concurrent search test
    try:
        result = tester.concurrent_search_test(num_threads=10, queries_per_thread=50)
        results["tests"].append(result)
        print("DONE")
    except Exception as e:
        print(f"FAILED: {e}")
        results["tests"].append({"test": "concurrent_search", "error": str(e)})

    # Concurrent retrieval test
    try:
        result = tester.concurrent_retrieval_test(num_threads=10, retrievals_per_thread=100)
        results["tests"].append(result)
        print("DONE")
    except Exception as e:
        print(f"FAILED: {e}")
        results["tests"].append({"test": "concurrent_retrieval", "error": str(e)})

    # Batch stress test
    try:
        result = tester.batch_stress_test(batch_sizes=[5, 10, 15])
        results["tests"].append(result)
        print("DONE")
    except Exception as e:
        print(f"FAILED: {e}")
        results["tests"].append({"test": "batch_stress", "error": str(e)})

    # Mixed workload test
    try:
        result = tester.mixed_workload_test(duration_seconds=5)
        results["tests"].append(result)
        print("DONE")
    except Exception as e:
        print(f"FAILED: {e}")
        results["tests"].append({"test": "mixed_workload", "error": str(e)})

    print()
    print("=" * 60)
    print("Load Test Results")
    print("=" * 60)

    for test_result in results["tests"]:
        print()
        print(f"Test: {test_result.get('test', 'unknown')}")

        if "error" in test_result:
            print(f"  ERROR: {test_result['error']}")
            continue

        for key, value in test_result.items():
            if key == "test":
                continue

            if isinstance(value, float):
                print(f"  {key}: {value:.3f}")
            elif isinstance(value, list):
                print(f"  {key}: [{len(value)} items]")
            else:
                print(f"  {key}: {value}")

    return results


if __name__ == "__main__":
    try:
        results = run_load_tests()

        # Save to JSON
        output_path = project_root / "benchmarks" / "load_test_results.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print()
        print(f"Results saved to: {output_path}")

    except Exception as e:
        print(f"Error running load tests: {e}")
        import traceback

        traceback.print_exc()

        # Save error to JSON
        error_output = {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "traceback": traceback.format_exc(),
        }

        output_path = project_root / "benchmarks" / "load_test_results.json"
        with open(output_path, "w") as f:
            json.dump(error_output, f, indent=2)

        sys.exit(1)
