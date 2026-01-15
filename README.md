# MetaMCP Server

[![CI](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/itstanner5216/MetaServer/branch/main/graph/badge.svg)](https://codecov.io/gh/itstanner5216/MetaServer)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Meta MCP Server - FastMCP-based server infrastructure with progressive tool discovery and governance.

## 🤖 Automated Setup

### Quick Setup

```bash
# Clone repository
git clone https://github.com/itstanner5216/MetaServer.git
cd MetaServer

# Run automated setup
bash scripts/setup.sh

# Configure GitHub secrets (optional)
bash scripts/gh-setup-secrets.sh
```

### What Gets Automated

- ✅ Dependency installation via UV
- ✅ Pre-commit hook installation (if configured)
- ✅ Branch protection rules
- ✅ Repository labels and settings
- ✅ Automated security fixes
- ✅ Code scanning with CodeQL

### Manual Steps

Some integrations require one-time manual setup:

1. **Codecov:** Sign up and add repository token to secrets
2. **PyPI:** Configure trusted publishing for releases

Run the setup validation to check status:
```bash
gh workflow run validate-setup.yml
```

## 🤖 AI Agent System for PR Management

MetaServer includes a **fully automated multi-agent system** for validating, fixing, and bundling pull requests:

### Features

- **Automated PR Validation** 🔍: Validates all open PRs with tests, security scans, and architectural checks
- **Auto-Remediation** 🔧: Automatically fixes common issues (imports, conflicts, simple test failures)
- **Architectural Guardian** 🏛️: Ensures no breaking changes or architectural violations
- **Meta-PR Creation** 📦: Groups safe PRs by functional area into reviewable meta-PRs
- **Functional Verification** ✅: Verifies meta-PRs don't break server functionality
- **Comprehensive Reporting** 📊: Generates detailed reports and action items

### Quick Start

Run the full validation system via GitHub Actions:

1. Go to **Actions** → **🤖 Intelligent PR Validation & Auto-Remediation**
2. Click **Run workflow**
3. Select options (auto-fix, architectural checks, create meta-PRs)
4. Review the generated reports and meta-PRs

### Documentation

See **[docs/AGENT_SYSTEM.md](docs/AGENT_SYSTEM.md)** for complete documentation including:
- System architecture and agent details
- Usage instructions and examples
- Safety mechanisms and rollback procedures
- Troubleshooting guide

### Benefits

- ✅ **Save 40+ hours** of manual PR review time
- ✅ **Eliminate breaking changes** through automated architectural analysis
- ✅ **Auto-fix common issues** with remediation agent
- ✅ **Bundle related changes** for easier review
- ✅ **Maintain code quality** with comprehensive validation

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
- GNOME Shell extension (installation notes forthcoming)

**Fallback Options:**
If GUI approval is not available, the system automatically falls back to:
1. FastMCP `ctx.elicit()` (if supported by client)
2. systemd-ask-password (terminal-based prompt)

#### Development Tools

```bash
# Install with development dependencies (using UV - recommended)
uv sync --all-extras

# Or with pip
pip install -e ".[dev]"
```

## Development Setup

### Prerequisites
- Python 3.10 or higher
- [UV](https://github.com/astral-sh/uv) package manager (recommended for faster installs)

### Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/itstanner5216/MetaServer.git
   cd MetaServer
   ```

2. Install dependencies:
   ```bash
   uv sync --all-extras
   ```

3. Install pre-commit hooks:
   ```bash
   uv run pre-commit install
   ```

4. Run tests:
   ```bash
   uv run pytest
   ```

### Development Commands

**Linting:**
```bash
uv run ruff check .          # Check for issues
uv run ruff check . --fix    # Auto-fix issues
```

**Formatting:**
```bash
uv run ruff format .         # Format code
```

**Type Checking:**
```bash
uv run pyright               # Type check
```

**Testing:**
```bash
uv run pytest                # Run all tests
uv run pytest -v             # Verbose output
uv run pytest --cov          # With coverage
```

**Pre-commit:**
```bash
uv run pre-commit run --all-files  # Run all hooks
```
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

# Audit logging
export AUDIT_LOG_PATH="./audit.jsonl"
export AUDIT_LOG_MAX_BYTES="10485760"    # Rotate after ~10MB
export AUDIT_LOG_BACKUP_COUNT="5"        # Retain 5 rotated files

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
`DEFAULT_MODE` is deprecated and will be removed in a future release.

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
- `AGENT_ARCHITECTURE_DESIGN.md` - Architecture design for the agent runtime and governance integration
- `tests/SECURITY_TESTS_README.md` - Security test coverage and execution notes
- `config/client_configs.md` - Client configuration examples

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
