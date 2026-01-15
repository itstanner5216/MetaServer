"""
Entry point for running meta_mcp as a module.

Allows running the Meta MCP Server via:
    python -m meta_mcp
    uv run python -m meta_mcp
"""

from meta_mcp.supervisor import main

if __name__ == "__main__":
    main()
