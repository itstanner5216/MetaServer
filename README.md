# MetaServer

**Capability security for AI agents.**

[![CI](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/itstanner5216/MetaServer/branch/main/graph/badge.svg)](https://codecov.io/gh/itstanner5216/MetaServer)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [FastMCP](https://github.com/jlowin/fastmcp)-based MCP server that gives enterprises control over what tools AI agents can access, for how long, and with full accountability. Standard MCP servers expose every tool to every agent, all the time — MetaServer inverts that default.

- 🔍 **Progressive tool discovery** — only 2 bootstrap tools visible at startup; everything else is hidden until explicitly requested (86.7% context reduction)
- 🔐 **Lease-based access (TTL + calls)** — time-limited, call-budgeted, HMAC-SHA256 signed leases scoped per session and tool
- ✅ **Approvals + audit logging** — tri-state governance (`READ_ONLY` / `PERMISSION` / `BYPASS`), scoped approval flow, every decision logged

---

## 60-Second Proof: Progressive Discovery in Action

An agent connects and sees **only two tools**. Here is the full flow to discover, unlock, and use a tool:

```
┌─ 1. LIST TOOLS ──────────────────────────────────────────────────┐
│  Agent calls tools/list                                          │
│  → Only sees: search_tools, get_tool_schema                     │
│  → 13 other tools are hidden (86.7% context reduction¹)         │
└──────────────────────────────────────────────────────────────────┘

┌─ 2. SEARCH ──────────────────────────────────────────────────────┐
│  agent → search_tools("read file")                               │
│       ← [{ tool: "read_file",                                    │
│             description: "Read file contents from workspace",    │
│             risk: "safe" }]                                      │
│  → Metadata only — tool is still NOT in tools/list               │
└──────────────────────────────────────────────────────────────────┘

┌─ 3. GET SCHEMA → TOOL EXPOSED + LEASE ISSUED ───────────────────┐
│  agent → get_tool_schema("read_file")                            │
│       ← { name, description, inputSchema }                      │
│  → Tool is now visible in tools/list                             │
│  → Lease granted: TTL 5 min, 3 calls, HMAC-SHA256 token issued  │
└──────────────────────────────────────────────────────────────────┘

┌─ 4. CALL TOOL → LEASE CONSUMED + AUDIT LOGGED ──────────────────┐
│  agent → read_file(path="data.txt")                              │
│       ← file contents                                            │
│  → Lease call count decremented atomically (Redis Lua script)    │
│  → Audit entry written: tool_invoked, client, timestamp          │
└──────────────────────────────────────────────────────────────────┘

┌─ 5. LEASE EXPIRES → TOOL DISAPPEARS ────────────────────────────┐
│  → After TTL or call budget exhausted, tool removed from         │
│    tools/list automatically — no stale tool lists                │
└──────────────────────────────────────────────────────────────────┘
```

> ¹ **86.7% context reduction**: 2 bootstrap tools visible out of 15 total registered tools (defined in [`config/tools.yaml`](config/tools.yaml)). Calculated as `(15 − 2) / 15 = 86.7%` tools hidden at startup.

---

## Quick Start

### Prerequisites
- Python 3.10+
- Redis (for lease management and governance state)
- [UV](https://github.com/astral-sh/uv) package manager (recommended)

> **Note:** No AI model API keys are required. MetaServer is an MCP server — it governs tool access for agents, it does not run models itself.

### Install

```bash
git clone https://github.com/itstanner5216/MetaServer.git
cd MetaServer

# Automated setup (deps, pre-commit hooks, validation)
bash scripts/setup.sh

# Or manual install
uv sync --all-extras
```

### Run

```bash
uv run python -m meta_mcp
```

The server starts on `http://localhost:8001` (SSE transport, Docker-compatible).

### Connect an Agent

Point any MCP-compatible client at `http://localhost:8001/sse`. The agent sees only `search_tools` and `get_tool_schema` — everything else is discovered on demand:

```
agent → search_tools("read file")
     ← [read_file: "Read file contents from workspace" | safe]

agent → get_tool_schema("read_file")
     ← { name, description, inputSchema }   # tool is now in tools/list

agent → read_file(path="data.txt")
     ← file contents
```

---

## Security

### Production Checklist

1. **Generate a strong HMAC secret:**
   ```bash
   python -c "import os; print(os.urandom(64).hex())"
   ```
2. **Secure Redis:** password-protect and network-isolate your Redis instance
3. **Set governance mode:** use `PERMISSION` (default) or `READ_ONLY` in production; never `BYPASS`
4. **Review audit logs:** `audit.jsonl` contains every governance decision
5. **Restrict workspace:** ensure `WORKSPACE_ROOT` permissions are locked down to the server process

### Security Properties

| Property | Implementation |
|----------|---------------|
| Path traversal prevention | `path.relative_to(workspace)` — raises before any I/O |
| Token forgery prevention | HMAC-SHA256 with constant-time comparison |
| Cross-session token reuse | Tokens bound to `(client_id, tool_id)` |
| Replay attack prevention | Token expiration enforced on every verify |
| Lease race conditions | Atomic Lua script for consume (no TOCTOU) |
| Fail-closed defaults | Unknown mode/risk → `require_approval`; lease errors → deny |
| Scoped permissions | Elevations are `SHA256(tool+path+session)`, not global |

### Approval Scope Format

Scopes follow a `type:value` pattern:
- `tool:write_file` — permission to call a specific tool
- `filesystem:write` — permission category
- `resource:path:/workspace/data.txt` — permission for a specific resource

The middleware enforces that **all required scopes are selected** and **no extra scopes are granted** (preventing privilege escalation via approval).

---

## Configuration

Create a `.env` file or set environment variables:

```bash
# ── Server ──────────────────────────────────────────────
HOST=0.0.0.0
PORT=8001
WORKSPACE_ROOT=./workspace

# ── Redis ───────────────────────────────────────────────
REDIS_URL=redis://localhost:6379
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_CONNECT_TIMEOUT=2
REDIS_CONNECT_RETRIES=3

# ── Governance ──────────────────────────────────────────
DEFAULT_GOVERNANCE_MODE=permission   # read_only | permission | bypass

# ── Capability Tokens ───────────────────────────────────
# Generate: python -c "import os; print(os.urandom(64).hex())"
HMAC_SECRET=your-64-byte-hex-key-here

# ── Audit Logging ───────────────────────────────────────
AUDIT_LOG_PATH=./audit.jsonl
AUDIT_LOG_MAX_BYTES=10485760         # 10 MB rotation
AUDIT_LOG_BACKUP_COUNT=5             # retain 5 rotated files
AUDIT_LOG_BUFFER_SIZE=100            # buffer before flush
AUDIT_LOG_FLUSH_INTERVAL=1.0        # seconds between flushes

# ── Approval Provider ───────────────────────────────────
APPROVAL_PROVIDER=auto               # auto | dbus_gui | fastmcp_elicit | systemd_fallback

# ── TOON Encoding ───────────────────────────────────────
TOON_ARRAY_THRESHOLD=5               # arrays longer than this are compressed

# ── Feature Flags ───────────────────────────────────────
ENABLE_LEASE_MANAGEMENT=true
ENABLE_MACROS=true
ENABLE_SEMANTIC_RETRIEVAL=false      # requires Qdrant + Gemini API key
ENABLE_PROGRESSIVE_SCHEMAS=false     # minimal schema delivery
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Client (AI Agent)                 │
└────────────────────────┬────────────────────────────────┘
                         │ MCP over HTTP/SSE
┌────────────────────────▼────────────────────────────────┐
│                  MetaSupervisor (FastMCP)                │
│                                                         │
│  Bootstrap Tools (always visible):                      │
│    search_tools()  ──→  ToolRegistry (YAML)             │
│    get_tool_schema() ─→  Expose tool + Grant Lease      │
│                                                         │
│  GovernanceMiddleware (every tool call):                │
│    ├─ Lease validation (Redis)                          │
│    ├─ Elevation check (Redis)                           │
│    ├─ Policy evaluation (tri-state matrix)              │
│    ├─ Approval elicitation (if needed)                  │
│    ├─ Capability token verification (HMAC-SHA256)       │
│    ├─ Tool execution                                    │
│    ├─ TOON output encoding                              │
│    └─ Audit logging (JSON Lines)                        │
│                                                         │
│  Mounted Servers:                                       │
│    CoreTools  (file, directory, shell, git)             │
│    AdminTools (governance mode, elevations)             │
└────────────────────────┬────────────────────────────────┘
                         │
              ┌──────────┴───────────┐
              │                      │
    ┌─────────▼──────────┐  ┌───────▼────────┐
    │   Redis             │  │  Qdrant         │
    │   - Leases (TTL)    │  │  - RAG chunks   │
    │   - Elevations      │  │  - Embeddings   │
    │   - Gov. mode       │  └────────────────┘
    └────────────────────┘
```

---

## Deep Dive

<details>
<summary><strong>Tools</strong> — 15 tools across 2 servers, risk-classified</summary>

### Core Tools (`core_tools` server)

| Tool | Risk | Description |
|------|------|-------------|
| `read_file` | safe | Read file contents from workspace |
| `list_directory` | safe | List directory contents with type indicators |
| `write_file` | sensitive | Write content to file in workspace |
| `create_directory` | sensitive | Create directory (including parents) |
| `move_file` | sensitive | Move or rename file within workspace |
| `execute_command` | sensitive | Execute shell command with 30s timeout |
| `git_commit` | sensitive | Commit staged changes with message |
| `git_push` | sensitive | Push commits to remote repository |
| `delete_file` | dangerous | Permanently delete a file |
| `remove_directory` | dangerous | Recursively remove directory and all contents |
| `git_reset` | dangerous | Reset repository to a specific ref |

### Admin Tools (`admin_tools` server)

| Tool | Risk | Description |
|------|------|-------------|
| `get_governance_status` | safe | Get current mode, active elevations, statistics |
| `set_governance_mode` | sensitive | Switch governance mode at runtime |
| `revoke_all_elevations` | dangerous | Clear all active permission elevations |

Plus **2 bootstrap tools** (`search_tools`, `get_tool_schema`) always visible. Full definitions in [`config/tools.yaml`](config/tools.yaml).

</details>

<details>
<summary><strong>Governance System</strong> — tri-state policy matrix + scoped approvals</summary>

### Policy Matrix

```
             SAFE       SENSITIVE    DANGEROUS
READ_ONLY  │ Allow   │  Block     │  Block
PERMISSION │ Allow   │  Approval  │  Approval
BYPASS     │ Allow   │  Allow     │  Allow
```

Unknown risk levels and unknown modes always fail to `require_approval` (fail-safe).

### Approval Flow (PERMISSION mode)

When a sensitive tool is called without an active elevation:

1. Middleware generates a scoped `ApprovalRequest` with required permission scopes
2. Approval request is sent to the configured provider (GUI / elicit / terminal)
3. User selects which scopes to grant and sets a lease duration
4. If approved: scoped elevation is stored in Redis with TTL; tool executes
5. If denied / timeout: `ToolError` is raised; nothing executes

### Multi-Provider Approval

Three providers are supported, with automatic fallback:
1. **GNOME DBus GUI** — Desktop notification with scope selection (Wayland/GNOME Shell)
2. **FastMCP `ctx.elicit()`** — In-client approval prompt with structured response parsing
3. **systemd-ask-password** — Terminal fallback for headless environments

### Elicitation Response Format

When using `FastMCP ctx.elicit()`, the client responds with:

**JSON format:**
```json
{
  "decision": "approved",
  "selected_scopes": ["tool:write_file", "resource:path:/workspace/report.txt"],
  "lease_seconds": 300
}
```

**Key-value format:**
```
decision=approved
selected_scopes=tool:write_file, resource:path:/workspace/report.txt
lease_seconds=300
```

Set `lease_seconds=0` for single-use approval.

### Scoped Elevations

Elevations are scoped to `SHA256(tool_name + context_key + session_id)`. This means an elevation for `write_file` on `/workspace/foo.txt` does **not** grant access to `/workspace/bar.txt`. Every resource gets its own elevation slot.

</details>

<details>
<summary><strong>Lease Management</strong> — Redis-backed ephemeral leases with atomic operations</summary>

Leases are the authorization primitive. Every tool access requires an active lease:

```
grant(client_id, tool_id, ttl, calls)  →  ToolLease stored in Redis
validate(client_id, tool_id)            →  ToolLease if valid, None if expired
consume(client_id, tool_id)            →  Atomic decrement via Lua script
revoke(client_id, tool_id)             →  Manual deletion
purge_expired()                         →  Batch cleanup of expired keys
```

Risk-based defaults:

| Risk Level | TTL | Max Calls |
|-----------|-----|-----------|
| safe | 5 min | 3 |
| sensitive | 5 min | 1 |
| dangerous | 2 min | 1 |

The `consume` operation uses a Lua script for atomic decrement and deletion — a lease cannot be double-spent even under concurrent access.

</details>

<details>
<summary><strong>Capability Tokens</strong> — HMAC-SHA256 signed, session-bound</summary>

Every lease is backed by an HMAC-SHA256 signed capability token:

```
Token = base64(payload_json) . hmac_sha256(payload_bytes, secret)

Payload = {
  "client_id": "...",
  "tool_id":   "...",
  "iat":       <unix_timestamp>,
  "exp":       <unix_timestamp + ttl>,
  "context_key": "..."  (optional)
}
```

Verification checks:
1. Format is valid (exactly two `.`-separated parts)
2. Base64 encoding is canonical (no padding variants accepted)
3. Payload JSON is canonically encoded (RFC 8785 — sorted keys, no whitespace)
4. HMAC signature matches (constant-time comparison)
5. Token is not expired
6. `client_id` matches the requesting session
7. `tool_id` matches the requested tool
8. `context_key` matches (if present)

Any failure → token rejected, access denied.

</details>

<details>
<summary><strong>RAG Pipeline</strong> — hybrid semantic + BM25 retrieval with governance-aware ranking</summary>

### Ingestion (`src/meta_mcp/rag/ingestion/`)
- `SemanticChunker` — splits documents by structure (Markdown headings, paragraph breaks) then by token count with configurable overlap
- Each chunk gets a SHA-256 hash for deduplication
- Token counting via `tiktoken` (`cl100k_base` encoding — same as GPT-4; used as an approximation since Gemini uses its own tokenization scheme)

### Embedding (`src/meta_mcp/rag/embedding/`)
- `GeminiEmbedderAdapter` — 768-dimension dense vectors
- Pre-allocation pool for batch embedding efficiency
- TTL-based query embedding cache (default 60s, up to 100 entries)

### Storage (`src/meta_mcp/rag/storage/`)
- `QdrantStorageClient` — vector DB with scope-level filtering
- Manifest tracking for ingested documents

### Retrieval (`src/meta_mcp/rag/retrieval/`)
- `SemanticRetriever` — hybrid search combining:
  - Qdrant ANN for semantic similarity (cosine)
  - BM25 lexical index (lazily built per scope, auto-rebuilt on scope change)
  - Weighted combination: 60% semantic + 40% BM25 (configurable)
- Governance-aware re-ranking:
  - `READ_ONLY`: dangerous tool scores → 0.0, sensitive → 0.1
  - `PERMISSION`: dangerous → 0.5, sensitive → 0.8
  - `BYPASS`: all → 1.0
- Latency target: **170 ms** per query

### Context Packing (`src/meta_mcp/rag/context_pack/`)
- Assembles retrieved chunks into a validated context package for agent consumption

</details>

<details>
<summary><strong>TOON Output Encoding</strong> — context-safe array compression</summary>

Large tool outputs can blow up an agent's context window. TOON (Threshold-Optimized Output Notation) prevents this by replacing long arrays with metadata summaries:

```python
# Input (6-item array, threshold=5)
{"files": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"]}

# TOON output
{"files": {"__toon": true, "count": 6, "sample": ["a.py", "b.py", "c.py"]}}
```

- Recursive — handles nested dicts, lists, and tuples
- Threshold configurable via `TOON_ARRAY_THRESHOLD` (default: 5)
- Applied to all tool responses in the middleware layer
- Fails safely — original output returned if encoding fails

</details>

<details>
<summary><strong>Macro Operations</strong> — batch primitives for high-throughput workflows</summary>

- **`batch_read_tools(registry, tool_ids, max_risk_level)`** — retrieve multiple tool records in one call, with optional risk-level filtering
- **`batch_write`** — bulk workspace writes
- **`batch_search`** — run multiple search queries and deduplicate results

Macros respect the same governance and risk-level constraints as individual tool calls.

</details>

---

## Developer Tooling

### AI Agent Pipeline *(Optional)*

> **This is an optional add-on.** The core MetaServer (progressive discovery, governance, leases, capability tokens, audit) requires no AI model API keys. The agent pipeline below is a separate feature for teams that want automated PR validation on top of MetaServer.

MetaServer includes a **multi-agent PR validation system** that plugs into GitHub Actions. Agent↔model bindings are configured via [`config/models.yaml`](config/models.yaml) — no code changes required to swap providers.

| Agent | Role |
|-------|------|
| **Validator** | Reviews PRs for code quality, security patterns, and architectural checks |
| **Remediator** | Auto-fixes common issues (imports, conflicts, simple test failures) |
| **Architectural Guardian** | Rejects breaking changes or structural violations |
| **Functional Verifier** | Validates end-to-end functionality of meta-PRs |

#### Running the Pipeline

Via GitHub Actions:
1. Go to **Actions** → **🤖 Intelligent PR Validation & Auto-Remediation**
2. Click **Run workflow**
3. Select options (auto-fix, architectural checks, create meta-PRs)
4. Review the generated reports and meta-PRs

Via CLI:
```bash
python -m scripts.agents.run_agent --pr 123 --all --dry-run
```

Remove `--dry-run` to post actual GitHub comments and create PRs.

See [`docs/AI_AGENT_PIPELINE.md`](docs/AI_AGENT_PIPELINE.md) and [`examples/ai_agent_quick_start.py`](examples/ai_agent_quick_start.py) for full usage.

### Development Setup

```bash
git clone https://github.com/itstanner5216/MetaServer.git
cd MetaServer
uv sync --all-extras
uv run pre-commit install
```

### Commands

```bash
# Lint
uv run ruff check .
uv run ruff check . --fix

# Format
uv run ruff format .

# Type check
uv run pyright

# Test
uv run pytest
uv run pytest -v --cov=src/meta_mcp

# All pre-commit hooks
uv run pre-commit run --all-files
```

### Optional: GUI Approval Support

Requires GNOME Shell 40+ on Wayland with DBus session access:

```bash
pip install -e ".[gui-approval]"
```

Automatic fallback to `ctx.elicit()` → `systemd-ask-password` when not available.

### Testing

```bash
# Full test suite
uv run pytest

# With coverage report
uv run pytest --cov=src/meta_mcp --cov-report=html

# Specific test areas
uv run pytest tests/test_lease_manager.py       # lease system
uv run pytest tests/test_governance_modes.py    # governance matrix
uv run pytest tests/test_capability_tokens.py   # HMAC tokens
uv run pytest tests/test_semantic_search.py     # RAG retrieval
uv run pytest tests/integration/               # end-to-end flows
```

Test infrastructure uses `pytest-asyncio` in auto mode. Redis-dependent tests are marked `@pytest.mark.requires_redis` and API-dependent tests are marked `@pytest.mark.requires_api_keys`.

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture/AGENT_ARCHITECTURE_DESIGN.md`](docs/architecture/AGENT_ARCHITECTURE_DESIGN.md) | Agent runtime design, subagent architecture |
| [`docs/architecture/SECURITY_BOUNDARY.md`](docs/architecture/SECURITY_BOUNDARY.md) | Security boundary definitions and trust model |
| [`docs/AI_AGENT_PIPELINE.md`](docs/AI_AGENT_PIPELINE.md) | AI agent pipeline for PR management (optional) |
| [`docs/AGENT_SYSTEM.md`](docs/AGENT_SYSTEM.md) | Multi-agent system for automated PR review |
| [`docs/development/CONTRIBUTING.md`](docs/development/CONTRIBUTING.md) | Contribution guidelines |
| [`docs/development/TESTING.md`](docs/development/TESTING.md) | Testing strategy and coverage |
| [`tests/SECURITY_TESTS_README.md`](tests/SECURITY_TESTS_README.md) | Security test coverage matrix |
| [`examples/ai_agent_quick_start.py`](examples/ai_agent_quick_start.py) | Quick start example for the agent pipeline |

---

## License

This project is licensed under the [MIT License](LICENSE).