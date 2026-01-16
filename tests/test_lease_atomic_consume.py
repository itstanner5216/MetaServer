import asyncio

import pytest

from src.meta_mcp.leases.manager import lease_manager


@pytest.mark.requires_redis
@pytest.mark.asyncio
async def test_atomic_consume_prevents_overconsumption(redis_client):
    lease_manager._redis_client = redis_client
    try:
        lease = await lease_manager.grant(
            client_id="test_client",
            tool_id="tool_atomic",
            ttl_seconds=30,
            calls_remaining=1,
            mode_at_issue="permission",
        )
        assert lease is not None

        results = await asyncio.gather(
            *(lease_manager.consume("test_client", "tool_atomic") for _ in range(5))
        )
        successes = [result for result in results if result is not None]

        assert len(successes) == 1
        assert successes[0].calls_remaining == 0

        remaining = await lease_manager.validate("test_client", "tool_atomic")
        assert remaining is None
    finally:
        lease_manager._redis_client = None
