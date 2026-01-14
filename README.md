# MetaMCP Server

Meta MCP Server - FastMCP-based server infrastructure with progressive tool discovery and governance.

## Installation

### Base Installation

```bash
# Clone the repository
git clone <repository-url>
cd MCPServer

# Install base dependencies
pip install -e .
```

### Optional Dependencies

#### GUI Approval Support

To enable GUI-based approval notifications (requires GNOME Shell on Linux with Wayland):

```bash
# Install with GUI approval support
pip install -e ".[gui-approval]"
```

**Requirements for GUI Approval:**
- GNOME Shell (tested on version 40+)
- Wayland session
- DBus session bus access
- GNOME Shell extension (see `GUIPlan/` directory for installation)

**Fallback Options:**
If GUI approval is not available, the system automatically falls back to:
1. FastMCP `ctx.elicit()` (if supported by client)
2. systemd-ask-password (terminal-based prompt)

#### Development Tools

```bash
# Install with development dependencies
pip install -e ".[dev]"
```

## Configuration

### Environment Variables

Create a `.env` file or export the following:

```bash
# Redis (required for governance and lease management)
export REDIS_URL="redis://localhost:6379"

# HMAC secret for capability tokens (required for production)
export HMAC_SECRET="your-64-byte-hex-key"

# Workspace root directory
export WORKSPACE_ROOT="./workspace"

# Server configuration
export HOST="0.0.0.0"
export PORT="8001"

# Approval provider selection (optional)
# Options: dbus_gui, fastmcp_elicit, systemd_fallback, auto (default)
export APPROVAL_PROVIDER="auto"
```

### Governance Modes

The server supports three governance modes:

- **READ_ONLY**: Blocks all write operations completely
- **PERMISSION**: Requires approval for sensitive operations (default)
- **BYPASS**: Allows all operations (admin/dev mode only)

Set the default mode via:
```bash
export DEFAULT_GOVERNANCE_MODE="permission"
```

## Running the Server

```bash
# Start the server
python main.py
```

The server will start on `http://localhost:8001` by default.

## Architecture

### Progressive Tool Discovery

The server implements **Cognitive Sparsity** through progressive tool exposure:
- Bootstrap tools (always visible): `search_tools`, `get_tool_schema`
- All other tools (core, git, admin) are discovered via `search_tools()`
- Tools are exposed on-demand when `get_tool_schema()` is called
- Achieves 86.7% context reduction in tool visibility
- Admin tools are discoverable like other tools; approval is enforced at execution

### Lease Management

Tools require ephemeral leases with:
- Session-scoped access
- Time-to-live (TTL) based on risk level
- Call count limits
- Automatic expiration

### Governance & Approval

Sensitive operations trigger approval flows with:
- Scope selection (user chooses which permissions to grant)
- Lease duration control (user sets TTL)
- Scoped elevations (per-tool, per-resource, per-session)
- Audit logging of all decisions

#### FastMCP `ctx.elicit()` Response Format

When using the FastMCP approval provider, clients must respond to `ctx.elicit()` with
structured data that includes `selected_scopes` and `lease_seconds`. The server accepts
either JSON or key-value formats:

**JSON**
```json
{
  "decision": "approved",
  "selected_scopes": ["tool:write_file", "resource:path:/path/to/file"],
  "lease_seconds": 300
}
```

**Key-value (newline or semicolon separated)**
```
decision=approved
selected_scopes=tool:write_file, resource:path:/path/to/file
lease_seconds=300
```

Set `lease_seconds` to `0` for single-use approval. The middleware still enforces that
all required scopes must be selected and rejects any extra scopes.

## Documentation

### Core Documentation
- `.MCP/DEVELOPER_REFERENCE.md` - Complete developer guide with patterns and gotchas
- `.MCP/ARCHITECTURE_MAP.md` - Directory structure and component layout
- `.MCP/GAP_ANALYSIS_REPORT.md` - Implementation status and gaps
- `.MCP/IMPLEMENTATION_PLAN.md` - Current TODO lists and planning

### GUI Approval System
- `GUIPlan/APPROVAL_SYSTEM.md` - Complete GUI approval system guide
  - Approval provider architecture and selection
  - **Server-side scope enforcement** (ALL required scopes must be approved)
  - Lease semantics (single-use vs persistent elevations)
  - Security model and fail-safe defaults
  - Deployment guide and troubleshooting

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/meta_mcp --cov-report=html
```

## Security

⚠️ **Production Deployment:**
1. Generate a secure HMAC secret: `python -c "import os; print(os.urandom(64).hex())"`
2. Ensure Redis is secured (password, network isolation)
3. Set governance mode to PERMISSION or READ_ONLY
4. Review audit logs regularly
5. Keep workspace root permissions restricted

## License

[License information to be added]
