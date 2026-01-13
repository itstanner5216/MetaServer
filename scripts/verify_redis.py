#!/usr/bin/env python3
"""
Redis Connection Verification Script
Verifies Redis connectivity and basic operations using async client.
"""

import asyncio
import os
import sys
from redis import asyncio as aioredis


async def verify_connection():
    """
    Verify Redis connection and perform basic operations.

    Tests:
    - PING command
    - SET with TTL
    - GET
    - DELETE
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    print(f"Connecting to Redis at: {redis_url}")

    try:
        # Create Redis client
        redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True
        )

        # Test 1: PING command
        print("\n[1/4] Testing PING command...")
        response = await redis_client.ping()
        if response:
            print("✓ PING successful - received PONG")
        else:
            print("✗ PING failed - unexpected response")
            await redis_client.close()
            return False

        # Test 2: SET with TTL
        test_key = "test:verification:key"
        test_value = "verification_value"
        print(f"\n[2/4] Setting test key '{test_key}' with 10-second TTL...")
        await redis_client.setex(test_key, 10, test_value)
        print(f"✓ Successfully set key with TTL")

        # Test 3: GET and verify
        print(f"\n[3/4] Getting test key '{test_key}'...")
        retrieved_value = await redis_client.get(test_key)
        if retrieved_value == test_value:
            print(f"✓ Successfully retrieved and verified value: '{retrieved_value}'")
        else:
            print(f"✗ Value mismatch - expected '{test_value}', got '{retrieved_value}'")
            await redis_client.close()
            return False

        # Test 4: DELETE
        print(f"\n[4/4] Deleting test key '{test_key}'...")
        deleted = await redis_client.delete(test_key)
        if deleted:
            print(f"✓ Successfully deleted test key")
        else:
            print(f"✗ Failed to delete test key")

        # Close connection
        await redis_client.close()

        print("\n" + "="*50)
        print("✓ Redis Connection Status: OPERATIONAL")
        print("="*50)
        return True

    except aioredis.ConnectionError as e:
        print(f"\n✗ Redis Connection Error: {e}")
        print("  - Ensure Redis container is running")
        print("  - Verify REDIS_URL environment variable")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(verify_connection())
    sys.exit(0 if success else 1)
