#!/usr/bin/env python3
"""
[DEPRECATED] Migrate tool definitions from discovery.py to tools.yaml format.

⚠️ WARNING: This script is DEPRECATED and kept for reference only.
⚠️ The tools.yaml file already exists and is the canonical source of truth.
⚠️ Use config/tools.yaml directly for tool definitions.

This script was used for the one-time migration from discovery.py to tools.yaml.
It should NOT be used for regular tool management.

Legacy functionality:
1. Extracts all tool registrations from discovery.py
2. Maps old fields to new ToolRecord schema
3. Generates complete tools.yaml with proper structure
4. Validates output against new schema requirements

Usage (not recommended):
    python scripts/migrate_tools_to_yaml.py [--output config/tools.yaml]
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from meta_mcp.discovery import tool_registry


def map_category_to_server_id(category: str) -> str:
    """Map old category to new server_id."""
    mapping = {
        "core": "core_tools",
        "git": "git_tools",
        "admin": "admin_tools",
        "search": "core_tools",  # Meta tools go to core
    }
    return mapping.get(category, f"{category}_tools")


def map_sensitivity_to_risk(sensitive: bool, name: str) -> str:
    """
    Map old sensitive flag to new risk level.

    Rules:
    - sensitive=False → risk="safe"
    - sensitive=True → risk="sensitive" or "dangerous"
    - "dangerous" reserved for: delete, reset, revoke operations
    """
    if not sensitive:
        return "safe"

    # Dangerous operations (destructive)
    dangerous_keywords = ["delete", "reset", "revoke", "remove", "destroy"]
    if any(keyword in name.lower() for keyword in dangerous_keywords):
        return "dangerous"

    # Default sensitive
    return "sensitive"


def generate_tags(name: str, category: str, description: str) -> list[str]:
    """Generate tags based on tool name, category, and description."""
    tags = []

    # Category tag
    tags.append(category)

    # Extract operation type from name
    name_parts = name.split("_")
    if len(name_parts) >= 2:
        operation = name_parts[0]  # read, write, list, delete, etc.
        if operation in [
            "read",
            "write",
            "list",
            "delete",
            "create",
            "move",
            "execute",
            "git",
            "set",
            "get",
        ]:
            tags.append(operation)

        # Subject (file, directory, command, etc.)
        subject = name_parts[1] if len(name_parts) >= 2 else None
        if subject in ["file", "directory", "command", "commit", "governance"]:
            tags.append(subject)

    # Special tags
    if "workspace" in description.lower():
        tags.append("workspace")

    if name in ["search_tools", "get_tool_schema"]:
        tags.extend(["meta", "discovery"])

    if "governance" in description.lower() or "admin" in category:
        tags.append("governance")

    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags


def expand_description(short_desc: str, name: str) -> str:
    """
    Expand short description into fuller description.

    Uses common patterns to add context.
    """
    # Remove trailing period for processing
    short_desc = short_desc.rstrip(".")

    # Expansion patterns
    expansions = {
        "read_file": f"{short_desc}.\nSupports text files with automatic encoding detection. Returns file contents as string.",
        "write_file": f"{short_desc}.\nCreates the file if it doesn't exist. Creates parent directories automatically if needed.",
        "list_directory": f"{short_desc}.\nShows files and subdirectories with type indicators (F=file, D=directory). Helps navigate the workspace structure.",
        "delete_file": f"{short_desc}.\nPermanently removes the file. This operation cannot be undone. Requires governance approval.",
        "create_directory": f"{short_desc}.\nCreates all parent directories if they don't exist. Safe operation that won't fail if directory already exists.",
        "move_file": f"{short_desc}.\nCan move files between directories or rename in place. Overwrites destination if it exists.",
        "execute_command": f"{short_desc}.\nRuns command in workspace directory with 30-second timeout. Returns stdout, stderr, and exit code.",
        "search_tools": f"{short_desc}.\nReturns tool candidates with metadata but not schemas. Use get_tool_schema() to access full tool details.",
        "get_tool_schema": f"{short_desc}.\nThis is the gateway to tool access - schemas are not visible until explicitly requested. Progressive discovery mechanism.",
        "git_commit": f"{short_desc}.\nCommits all staged changes with provided message. Requires changes to be staged first with git add.",
        "git_push": f"{short_desc}.\nPushes all commits from current branch to remote. Requires valid git credentials and remote configuration.",
        "git_reset": f"{short_desc}.\nResets the repository to specified commit or state. Can be destructive - use with caution.",
        "set_governance_mode": f"{short_desc}.\nSwitches between READ_ONLY, PERMISSION, and BYPASS modes. Affects all subsequent tool calls.",
        "get_governance_status": f"{short_desc}.\nReturns current mode, active elevations, and governance statistics.",
        "revoke_all_elevations": f"{short_desc}.\nClears all temporary permission grants. Resets all tools to base governance policy.",
    }

    return expansions.get(
        name, f"{short_desc}.\nPerforms {name.replace('_', ' ')} operation in the workspace."
    )


def extract_tools() -> list[dict[str, Any]]:
    """Extract all tools from current registry."""
    tools = []

    for summary in tool_registry.get_all_summaries():
        # Map fields
        server_id = map_category_to_server_id(summary.category)
        risk_level = map_sensitivity_to_risk(summary.sensitive, summary.name)
        tags = generate_tags(summary.name, summary.category, summary.description)
        description_full = expand_description(summary.description, summary.name)

        tool_dict = {
            "tool_id": summary.name,
            "server_id": server_id,
            "description_1line": summary.description,
            "description_full": description_full,
            "tags": tags,
            "risk_level": risk_level,
            "requires_permission": summary.sensitive,
        }

        tools.append(tool_dict)

    return tools


def extract_servers(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract unique servers from tools."""
    servers_by_id = {}

    for tool in tools:
        server_id = tool["server_id"]
        if server_id not in servers_by_id:
            # Infer server description from server_id
            descriptions = {
                "core_tools": "Core file and system operations",
                "git_tools": "Git version control operations",
                "admin_tools": "Administrative and governance tools",
            }

            # Infer server risk from tools
            tool_risks = [t["risk_level"] for t in tools if t["server_id"] == server_id]
            if "dangerous" in tool_risks:
                server_risk = "dangerous"
            elif "sensitive" in tool_risks:
                server_risk = "sensitive"
            else:
                server_risk = "safe"

            # Collect unique tags
            server_tags = set()
            for t in tools:
                if t["server_id"] == server_id:
                    server_tags.update(t["tags"])

            servers_by_id[server_id] = {
                "server_id": server_id,
                "description": descriptions.get(
                    server_id, f"{server_id.replace('_', ' ').title()}"
                ),
                "risk_level": server_risk,
                "tags": sorted(list(server_tags)),
            }

    return list(servers_by_id.values())


def generate_yaml(output_path: Path) -> None:
    """Generate tools.yaml from current registry."""
    print("Extracting tools from discovery.py...")

    # Extract tools
    tools = extract_tools()
    print(f"Found {len(tools)} tools")

    # Extract servers
    servers = extract_servers(tools)
    print(f"Found {len(servers)} servers")

    # Build YAML structure
    yaml_data = {
        "servers": servers,
        "tools": tools,
    }

    # Write YAML
    print(f"Writing to {output_path}...")
    with open(output_path, "w") as f:
        f.write("# MetaMCP Tool Registry\n")
        f.write("# Auto-generated from discovery.py\n")
        f.write("#\n")
        f.write("# This file defines all tools available in MetaMCP.\n")
        f.write("# Tools are loaded at startup and searchable via search_tools().\n")
        f.write("#\n")
        f.write("# Structure:\n")
        f.write("#   servers: List of MCP servers (logical groupings)\n")
        f.write("#   tools: List of tool definitions with metadata\n")
        f.write("#\n")
        f.write("# Risk Levels:\n")
        f.write("#   - safe: Read-only operations, no side effects\n")
        f.write("#   - sensitive: Write operations, requires governance approval\n")
        f.write("#   - dangerous: Destructive operations, requires explicit approval\n")
        f.write("\n")

        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False, width=100)

    print(f"✅ Generated {output_path}")

    # Print summary
    print("\nSummary:")
    print(f"  Servers: {len(servers)}")
    print(f"  Tools: {len(tools)}")
    print(f"  Bootstrap tools: {tool_registry.get_bootstrap_tools()}")

    # Print tool counts by risk level
    risk_counts = {"safe": 0, "sensitive": 0, "dangerous": 0}
    for tool in tools:
        risk_counts[tool["risk_level"]] += 1

    print("\n  Risk breakdown:")
    print(f"    Safe: {risk_counts['safe']}")
    print(f"    Sensitive: {risk_counts['sensitive']}")
    print(f"    Dangerous: {risk_counts['dangerous']}")


def validate_yaml(yaml_path: Path) -> bool:
    """Validate generated YAML against schema requirements."""
    print(f"\nValidating {yaml_path}...")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    errors = []

    # Validate structure
    if "servers" not in data:
        errors.append("Missing 'servers' key")
    if "tools" not in data:
        errors.append("Missing 'tools' key")

    # Validate servers
    for i, server in enumerate(data.get("servers", [])):
        if "server_id" not in server:
            errors.append(f"Server {i}: missing 'server_id'")
        if "description" not in server:
            errors.append(f"Server {i}: missing 'description'")
        if "risk_level" not in server:
            errors.append(f"Server {i}: missing 'risk_level'")
        elif server["risk_level"] not in ["safe", "sensitive", "dangerous"]:
            errors.append(f"Server {i}: invalid risk_level '{server['risk_level']}'")

    # Validate tools
    bootstrap_tools = {"search_tools", "get_tool_schema"}
    found_bootstrap = set()

    for i, tool in enumerate(data.get("tools", [])):
        # Required fields
        required = [
            "tool_id",
            "server_id",
            "description_1line",
            "description_full",
            "tags",
            "risk_level",
            "requires_permission",
        ]
        for field in required:
            if field not in tool:
                errors.append(f"Tool {i} ({tool.get('tool_id', 'unknown')}): missing '{field}'")

        # Validate risk_level
        if "risk_level" in tool and tool["risk_level"] not in ["safe", "sensitive", "dangerous"]:
            errors.append(f"Tool {i}: invalid risk_level '{tool['risk_level']}'")

        # Validate tags
        if "tags" in tool and not isinstance(tool["tags"], list):
            errors.append(f"Tool {i}: 'tags' must be a list")

        if "tags" in tool and len(tool["tags"]) == 0:
            errors.append(f"Tool {i}: 'tags' list is empty (must have at least one tag)")

        # Check bootstrap tools
        if tool.get("tool_id") in bootstrap_tools:
            found_bootstrap.add(tool["tool_id"])

    # Validate bootstrap tools exist
    if found_bootstrap != bootstrap_tools:
        missing = bootstrap_tools - found_bootstrap
        errors.append(f"Missing bootstrap tools: {missing}")

    # Print results
    if errors:
        print("❌ Validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    print("✅ Validation PASSED")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate tools from discovery.py to YAML")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/tools.yaml"),
        help="Output YAML file path (default: config/tools.yaml)",
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate existing YAML, don't generate"
    )

    args = parser.parse_args()

    if args.validate_only:
        if not args.output.exists():
            print(f"❌ File not found: {args.output}")
            sys.exit(1)

        valid = validate_yaml(args.output)
        sys.exit(0 if valid else 1)

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Generate YAML
    generate_yaml(args.output)

    # Validate
    validate_yaml(args.output)


if __name__ == "__main__":
    main()
