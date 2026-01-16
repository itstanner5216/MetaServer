import json
from datetime import datetime, timedelta, timezone

import pytest

from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.redis_client import close_redis_client, get_redis_client


@pytest.mark.requires_redis
@pytest.mark.asyncio
async def test_purge_expired_batches(redis_client):
    await redis_client.flushdb()
    await close_redis_client()
    lease_manager._redis_client = None

    redis = await get_redis_client()
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    for i in range(3):
        lease_dict = {
            "client_id": "test_client",
            "tool_id": f"tool_{i}",
            "granted_at": expired_at.isoformat(),
            "expires_at": expired_at.isoformat(),
            "calls_remaining": 1,
            "mode_at_issue": "permission",
            "capability_token": None,
        }
        await redis.set(f"lease:test_client:tool_{i}", json.dumps(lease_dict))

    purged = await lease_manager.purge_expired()
    assert purged == 3
