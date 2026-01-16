"""Deterministic performance regression tests."""

import os
import statistics
import time

import pytest

from src.meta_mcp.governance.policy import evaluate_policy
from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.retrieval.search import SemanticSearch
from src.meta_mcp.state import ExecutionMode, governance_state

LEASE_VALIDATION_BUDGET_SEC = float(os.getenv("LEASE_VALIDATION_BUDGET_SEC", "0.005"))
POLICY_EVAL_BUDGET_SEC = float(os.getenv("POLICY_EVAL_BUDGET_SEC", "0.002"))
SEARCH_GOV_BUDGET_SEC = float(os.getenv("SEARCH_GOV_BUDGET_SEC", "0.200"))
REDIS_ROUNDTRIP_BUDGET_SEC = float(os.getenv("REDIS_ROUNDTRIP_BUDGET_SEC", "0.010"))

median_seconds = statistics.median


@pytest.mark.asyncio
@pytest.mark.requires_redis
@pytest.mark.slow
async def test_lease_validation_latency_budget(redis_client):
    await lease_manager.grant(
        client_id="perf-client",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=100,
        mode_at_issue="PERMISSION",
    )

    for _ in range(10):
        await lease_manager.validate("perf-client", "read_file")

    samples = []
    for _ in range(50):
        start = time.perf_counter()
        await lease_manager.validate("perf-client", "read_file")
        samples.append(time.perf_counter() - start)

    median_latency = median_seconds(samples)
    assert median_latency <= LEASE_VALIDATION_BUDGET_SEC, (
        f"Lease validation median {median_latency:.6f}s exceeds budget "
        f"{LEASE_VALIDATION_BUDGET_SEC:.6f}s"
    )


def test_policy_evaluation_latency_budget():
    iterations = 20_000

    start = time.perf_counter()
    for _ in range(iterations):
        evaluate_policy(ExecutionMode.PERMISSION, "sensitive", "write_file")
    elapsed = time.perf_counter() - start

    per_call = elapsed / iterations
    assert per_call <= POLICY_EVAL_BUDGET_SEC, (
        f"Policy evaluation per-call {per_call:.6f}s exceeds budget "
        f"{POLICY_EVAL_BUDGET_SEC:.6f}s"
    )


@pytest.mark.asyncio
@pytest.mark.requires_redis
@pytest.mark.slow
async def test_search_with_governance_penalty_latency_budget(
    governance_in_permission,
    fresh_registry,
):
    registry = fresh_registry

    risk_levels = ["safe", "sensitive", "dangerous"]
    for index in range(240):
        risk_level = risk_levels[index % len(risk_levels)]
        registry.add_for_testing(
            ToolRecord(
                tool_id=f"perf_tool_{index}",
                server_id="perf_server",
                description_1line=f"Performance tool {index}",
                description_full=f"Performance tool {index} with {risk_level} risk",
                tags=["perf", "tool", risk_level],
                risk_level=risk_level,
            )
        )

    mode = await governance_state.get_mode()
    assert mode == ExecutionMode.PERMISSION

    searcher = SemanticSearch(registry)
    searcher.search("warmup")

    samples = []
    for _ in range(10):
        start = time.perf_counter()
        searcher.search("file operation")
        samples.append(time.perf_counter() - start)

    median_latency = median_seconds(samples)
    assert median_latency <= SEARCH_GOV_BUDGET_SEC, (
        f"Search median {median_latency:.6f}s exceeds budget "
        f"{SEARCH_GOV_BUDGET_SEC:.6f}s"
    )


@pytest.mark.asyncio
@pytest.mark.requires_redis
@pytest.mark.slow
async def test_redis_roundtrip_latency_budget(redis_client):
    await redis_client.ping()

    samples = []
    for _ in range(50):
        start = time.perf_counter()
        await redis_client.ping()
        samples.append(time.perf_counter() - start)

    median_latency = median_seconds(samples)
    assert median_latency <= REDIS_ROUNDTRIP_BUDGET_SEC, (
        f"Redis roundtrip median {median_latency:.6f}s exceeds budget "
        f"{REDIS_ROUNDTRIP_BUDGET_SEC:.6f}s"
    )
