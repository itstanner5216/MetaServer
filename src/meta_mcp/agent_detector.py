"""Agent ID detection for hook system integration.

Provides multiple strategies for extracting agent_id from FastMCP contexts.
"""

import os

from fastmcp import Context
from loguru import logger


def detect_agent_id(ctx: Context) -> str | None:
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
    if hasattr(ctx, "metadata") and ctx.metadata:
        agent_id = ctx.metadata.get("agent_id")
        if agent_id:
            logger.debug(f"Agent ID from metadata: {agent_id}")
            return agent_id

    # Strategy 2: Check request context (if already set)
    if hasattr(ctx, "request_context") and hasattr(ctx.request_context, "agent_id"):
        agent_id = ctx.request_context.agent_id
        if agent_id:
            logger.debug(f"Agent ID from request_context: {agent_id}")
            return agent_id

    # Strategy 3: Environment variable (simple single-agent deployments)
    agent_id = os.getenv("MCP_AGENT_ID")
    if agent_id:
        logger.debug(f"Agent ID from environment: {agent_id}")
        return agent_id

    # Strategy 4: Session mapping is reserved for a future Redis enhancement.

    # No agent mode
    return None


async def get_agent_id_for_session(session_id: str) -> str | None:
    """
    Get agent ID for a session from Redis storage.

    Stub: returns None. Redis-backed session→agent mapping is a planned
    enhancement.

    Args:
        session_id: Session identifier

    Returns:
        Agent ID if found, None otherwise
    """
    del session_id
    return None


async def set_agent_id_for_session(session_id: str, agent_id: str, ttl: int = 3600) -> bool:
    """
    Store agent ID for a session in Redis.

    Stub: returns False. Redis-backed session→agent mapping is a planned
    enhancement.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier to store
        ttl: Time-to-live in seconds (default 1 hour)

    Returns:
        True if stored successfully, False otherwise
    """
    del session_id, agent_id, ttl
    return False
