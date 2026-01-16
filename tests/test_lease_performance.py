"""
Performance regression tests for Phase 3+4 operations

Ensures lease and token operations meet performance targets:
- Lease grant: < 10ms
- Lease validate: < 5ms
- Lease consume: < 5ms
- Token generation: < 10ms
- Token verification: < 5ms
"""

import asyncio
import time

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance.tokens import generate_token, verify_token
from src.meta_mcp.leases import lease_manager


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_grant_performance(redis_client):
    """Test that lease grant completes in < 10ms."""
    iterations = 100

    start = time.perf_counter()
    for i in range(iterations):
        await lease_manager.grant(
            client_id=f"session_{i}",
            tool_id="test_tool",
            ttl_seconds=300,
            calls_remaining=3,
            mode_at_issue="PERMISSION",
        )
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 10, f"Lease grant too slow: {avg_ms:.2f}ms (target: <10ms)"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_validate_performance(redis_client):
    """Test that lease validation completes in < 5ms."""
    await lease_manager.grant(
        client_id="test_session",
        tool_id="test_tool",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        await lease_manager.validate("test_session", "test_tool")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 5, f"Lease validate too slow: {avg_ms:.2f}ms (target: <5ms)"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_consume_performance(redis_client):
    """Test that lease consumption completes in < 5ms."""
    await lease_manager.grant(
        client_id="test_session",
        tool_id="test_tool",
        ttl_seconds=300,
        calls_remaining=100,
        mode_at_issue="PERMISSION",
    )

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        await lease_manager.consume("test_session", "test_tool")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 5, f"Lease consume too slow: {avg_ms:.2f}ms (target: <5ms)"


def test_token_generation_performance():
    """Test that token generation completes in < 10ms."""
    iterations = 100

    start = time.perf_counter()
    for _ in range(iterations):
        generate_token(
            client_id="test_session",
            tool_id="test_tool",
            ttl_seconds=300,
            secret=Config.HMAC_SECRET,
        )
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 10, f"Token generation too slow: {avg_ms:.2f}ms (target: <10ms)"


def test_token_verification_performance():
    """Test that token verification completes in < 5ms."""
    token = generate_token(
        client_id="test_session",
        tool_id="test_tool",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        verify_token(token, "test_session", "test_tool", Config.HMAC_SECRET)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 5, f"Token verification too slow: {avg_ms:.2f}ms (target: <5ms)"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_concurrent_lease_operations(redis_client):
    """Test performance under concurrent load."""
    tasks = [
        lease_manager.grant(
            client_id=f"session_{i}",
            tool_id="test_tool",
            ttl_seconds=300,
            calls_remaining=3,
            mode_at_issue="PERMISSION",
        )
        for i in range(10)
    ]

    start = time.perf_counter()
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    elapsed_ms = elapsed * 1000
    assert elapsed_ms < 50, f"Concurrent grants too slow: {elapsed_ms:.2f}ms"
