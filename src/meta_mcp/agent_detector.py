"""Agent ID detection for hook system integration.

Provides multiple strategies for extracting agent_id from FastMCP contexts.
"""

import os
from typing import Optional

from fastmcp import Context
from loguru import logger


def detect_agent_id(ctx: Context) -> Optional[str]:
    """
    Extract agent_id from FastMCP context using multiple strategies.

    Checks (in priority order):
    1. Custom metadata in ctx.metadata (if your MCP client supports it)
    2. Environment variable (for single-agent deployments)
    3. Session-based mapping (future: could use Redis)

    Args:
        ctx: FastMCP context object

    Returns:
        Agent ID string if detected, None otherwise
    """
    # Strategy 1: Check MCP metadata (if client sends it)
    if hasattr(ctx, 'metadata') and ctx.metadata:
        agent_id = ctx.metadata.get('agent_id')
        if agent_id:
            logger.debug(f"Agent ID from metadata: {agent_id}")
            return agent_id

    # Strategy 2: Check request context (if already set)
    if hasattr(ctx, 'request_context') and hasattr(ctx.request_context, 'agent_id'):
        agent_id = ctx.request_context.agent_id
        if agent_id:
            logger.debug(f"Agent ID from request_context: {agent_id}")
            return agent_id

    # Strategy 3: Environment variable (simple single-agent deployments)
    agent_id = os.getenv('MCP_AGENT_ID')
    if agent_id:
        logger.debug(f"Agent ID from environment: {agent_id}")
        return agent_id

    # Strategy 4: Future - Redis session mapping
    # session_id = str(ctx.session_id)
    # Could lookup: AGENT_SESSION:{session_id} -> agent_id
    # This would require storing the mapping during session initialization

    # No agent mode
    return None


async def get_agent_id_for_session(session_id: str) -> Optional[str]:
    """
    Get agent ID for a session from Redis storage.

    THIS IS A FUTURE ENHANCEMENT - Currently just returns None.
    Implement this if you want Redis-backed session-to-agent mapping.

    Args:
        session_id: Session identifier

    Returns:
        Agent ID if found, None otherwise
    """
    # TODO: Implement Redis lookup
    # from .redis_client import get_redis_client
    # redis = await get_redis_client()
    # agent_id = await redis.get(f"agent_session:{session_id}")
    # return agent_id.decode() if agent_id else None
    return None


async def set_agent_id_for_session(session_id: str, agent_id: str, ttl: int = 3600) -> bool:
    """
    Store agent ID for a session in Redis.

    THIS IS A FUTURE ENHANCEMENT - Currently just returns False.
    Implement this if you want Redis-backed session-to-agent mapping.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier to store
        ttl: Time-to-live in seconds (default 1 hour)

    Returns:
        True if stored successfully, False otherwise
    """
    # TODO: Implement Redis storage
    # from .redis_client import get_redis_client
    # redis = await get_redis_client()
    # await redis.setex(f"agent_session:{session_id}", ttl, agent_id)
    # return True
    return False
