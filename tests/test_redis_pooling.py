import asyncio

import pytest

from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.redis_client import close_redis_client, get_redis_client
from src.meta_mcp.state import ExecutionMode, governance_state


@pytest.mark.requires_redis
@pytest.mark.asyncio
async def test_shared_pool_reuse(redis_client):
    await redis_client.flushdb()
    await close_redis_client()
    lease_manager._redis_client = None
    governance_state._redis_client = None

    async def run_governance():
        await governance_state.set_mode(ExecutionMode.PERMISSION)
        await governance_state.get_mode()

    async def run_lease(index: int):
        await lease_manager.grant(
            client_id="test_client",
            tool_id=f"tool_{index}",
            ttl_seconds=30,
            calls_remaining=1,
            mode_at_issue=ExecutionMode.PERMISSION.value,
        )

    await asyncio.gather(
        *(run_governance() for _ in range(3)),
        *(run_lease(i) for i in range(3)),
    )

    client = await get_redis_client()
    assert lease_manager._redis_client is governance_state._redis_client
    assert lease_manager._redis_client is client
    assert lease_manager._redis_client.connection_pool is client.connection_pool

    await close_redis_client()
