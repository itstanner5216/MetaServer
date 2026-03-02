# MetaServer

[![CI](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml/badge.svg)](https://github.com/itstanner5216/MetaServer/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/itstanner5216/MetaServer/branch/main/graph/badge.svg)](https://codecov.io/gh/itstanner5216/MetaServer)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Enterprise-grade MCP server with progressive tool discovery, tri-state governance, cryptographic capability tokens, and a built-in RAG pipeline — purpose-built to give AI agents the right tools at the right time, with complete auditability.**

---

## What is MetaServer?

MetaServer is a [FastMCP](https://github.com/jlowin/fastmcp)-based **Model Context Protocol (MCP) server** that solves a real problem enterprise teams run into when deploying AI agents: **tool sprawl and ungoverned access**.

Standard MCP servers expose every tool to every agent all the time. That means:
- Agents drown in irrelevant tools, wasting context window tokens
- Sensitive operations (file deletion, git reset, shell execution) sit one accidental tool call away
- There is no audit trail, no approval gate, no way to revoke access

MetaServer inverts this. Tools are **hidden by default** and only revealed when the agent specifically searches for them. Every sensitive operation is gated behind a governance policy, scoped approval, and a time-limited lease — all cryptographically signed and fully audited.

It is not finished — it is being built toward a complete enterprise agent runtime — but what is already here is deeply considered and production-ready at its core.

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Tools](#tools)
- [Governance System](#governance-system)
- [Lease Management](#lease-management)
- [Capability Tokens](#capability-tokens)
- [RAG Pipeline](#rag-pipeline)
- [TOON Output Encoding](#toon-output-encoding)
- [Macro Operations](#macro-operations)
- [AI Agent Pipeline](#ai-agent-pipeline)
- [Security](#security)
- [Development](#development)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Core Concepts

### Cognitive Sparsity
AI agents have a limited context window. Flooding an agent with 50 tool schemas at startup wastes tokens on tools it will never use. MetaServer exposes only **two bootstrap tools** at startup (`search_tools`, `get_tool_schema`). Every other tool is invisible until the agent explicitly requests it. This achieves **86.7% context reduction** in tool visibility.

### Tri-State Governance
Every tool call passes through a governance layer with three modes:

| Mode | Safe Tools | Sensitive Tools | Dangerous Tools |
|------|-----------|-----------------|-----------------|
| `READ_ONLY` | ✅ Allowed | 🚫 Blocked | 🚫 Blocked |
| `PERMISSION` | ✅ Allowed | ⏳ Approval required | ⏳ Approval required |
| `BYPASS` | ✅ Allowed | ✅ Allowed | ✅ Allowed |

The default mode is `PERMISSION`. The system **fails closed** — any unknown mode, failed lease, or missing elevation defaults to denial.

### Ephemeral Leases
Tool access is granted through time-limited leases stored in Redis. A lease encodes the client session, tool, TTL, and call budget. When the lease expires or the call budget is exhausted, access is automatically revoked. Leases are scoped per `(client_id, tool_id)` and can never be shared across sessions.

---

## Key Features

### 🔍 Progressive Tool Discovery
- Only `search_tools` and `get_tool_schema` are visible at startup
- Calling `get_tool_schema(tool_name)` triggers tool exposure + lease grant in one step
- Tools disappear from `tools/list` when leases expire — no stale tool lists
- Minimal schema mode reduces initial schema tokens further; agents can expand on demand with `get_tool_schema(expand=True)`

### 🛡️ Tri-State Governance Middleware
- `READ_ONLY` / `PERMISSION` / `BYPASS` modes switchable at runtime
- `GovernanceMiddleware` intercepts every tool call before execution
- Scoped elevations cached in Redis with TTL — per-tool, per-resource, per-session
- Full policy matrix evaluated deterministically before any execution

### 🔐 Cryptographic Capability Tokens
- Every lease is backed by an **HMAC-SHA256 signed capability token**
- Token payload: `{client_id, tool_id, exp, iat}` in RFC 8785 canonical JSON
- Constant-time comparison prevents timing attacks
- Tokens are bound to `(client_id, tool_id)` — cannot be reused across sessions or tools

### ⏱️ Redis-Backed Lease Manager
- Leases stored in Redis with native TTL for automatic expiration
- Atomic call-count decrement via Lua script (no race conditions)
- Risk-based TTL and call budgets:
  - `safe`: 5 minutes, 3 calls
  - `sensitive`: 5 minutes, 1 call
  - `dangerous`: 2 minutes, 1 call
- `list_changed` notifications emitted to clients on lease grant/revoke

### 📋 Structured Audit Trail
- Every governance decision logged to a rotating JSON Lines file (`audit.jsonl`)
- Events: `tool_invoked`, `approval_requested`, `approval_granted`, `approval_denied`, `approval_timeout`, `scoped_elevation_used`, `mode_changed`, `bypass_executed`, `blocked_read_only`
- Buffered async writes with configurable flush interval
- ISO 8601 UTC timestamps on every entry

### 🏗️ Multi-Provider Approval System
Sensitive operations trigger an approval flow. Three providers are supported, with automatic fallback:
1. **GNOME DBus GUI** — Desktop notification with scope selection (Wayland/GNOME Shell)
2. **FastMCP `ctx.elicit()`** — In-client approval prompt with structured response parsing
3. **systemd-ask-password** — Terminal fallback for headless environments

Approval responses select specific scopes and a lease duration. The middleware enforces that all required scopes are granted and rejects any extra scopes.

### 📦 TOON Output Encoding
**T**hreshold-**O**ptimized **O**utput **N**otation compresses large arrays in tool responses to prevent context overflow:
- Arrays longer than the threshold (default: 5) are replaced with `{__toon: true, count: N, sample: [first 3 items]}`
- Recursive — works on nested objects and tuples
- Configurable threshold per deployment
- Fails safely: returns the original output if encoding fails

### 🔎 Hybrid RAG Pipeline
A full retrieval-augmented generation system for tool documentation and context:
- **Ingestion**: Structure-aware chunking (Markdown headings, paragraph boundaries) with tiktoken-based token counting and SHA-256 chunk hashing
- **Embedding**: Gemini embedding adapter (768-dimension vectors), with TTL-based query embedding cache
- **Storage**: Qdrant vector database client with scope-filtered search
- **Retrieval**: Hybrid **semantic + BM25 lexical** search, weighted combination (default 60% semantic / 40% BM25)
- **Governance-aware ranking**: Score multipliers applied per governance mode — dangerous tools are penalized in `READ_ONLY` mode and ranked to zero in the results
- **Latency target**: 170 ms end-to-end retrieval

### ⚡ Macro Operations
Batch primitives for high-throughput agent workflows:
- `batch_read_tools` — Retrieve multiple tool records in a single call with risk-level filtering
- `batch_write` — Bulk write operations
- `batch_search` — Multi-query search with deduplication

### 🤖 Agent Runtime (In Progress)
MetaServer is being extended into a full **multi-agent runtime**:
- **YAML-driven agent↔model bindings** — each agent role locked to a specific model, no mid-run switching
- **Hook system** — pluggable gates at `before_tool_call`, `after_tool_result`, and `on_error` stages
- **Budget enforcement** — agent runs backed by leases, token budget tracked per run
- **4 specialized subagents**:
  - **Validator** — Tests, security scans, architectural review of PRs
  - **Remediator** — Auto-fixes common issues (imports, conflicts, test failures)
  - **Architectural Guardian** — Rejects breaking changes or structural violations
  - **Functional Verifier** — Validates end-to-end functionality of bundled PRs
- **Meta-PR creation** — Groups validated PRs by functional area into reviewable bundles

### 🔒 Workspace Sandboxing
All file and command operations are validated against `WORKSPACE_ROOT` using `path.relative_to()`. Path traversal attempts (`../../etc/passwd`) are rejected before execution.

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

## Quick Start

### Prerequisites
- Python 3.10 or higher
- Redis (for lease management and governance state)
- [UV](https://github.com/astral-sh/uv) package manager (recommended)

### Setup

```bash
# Clone the repository
git clone https://github.com/itstanner5216/MetaServer.git
cd MetaServer

# Automated setup (installs deps, pre-commit hooks, etc.)
bash scripts/setup.sh

# Or manual install
uv sync --all-extras
```

### Run the Server

```bash
# Start with UV (recommended)
uv run python -m meta_mcp

# Or with standard Python
python -m meta_mcp
```

The server starts on `http://localhost:8001` (SSE transport, Docker-compatible).

### Connect an Agent

Once running, point any MCP-compatible client at `http://localhost:8001/sse`. The agent will see only two tools: `search_tools` and `get_tool_schema`. From there, it can discover and access any tool through the progressive discovery flow:

```
agent → search_tools("read file")
     ← [read_file: "Read file contents from workspace" | safe]

agent → get_tool_schema("read_file")
     ← { name, description, inputSchema }   # tool is now in tools/list

agent → read_file(path="data.txt")
     ← file contents
```

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

## Tools

MetaServer ships with two tool groups:

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

---

## Governance System

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

---

## Lease Management

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

---

## Capability Tokens

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

---

## RAG Pipeline

MetaServer includes a full document retrieval system for grounding agent context:

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

---

## TOON Output Encoding

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

---

## Macro Operations

High-throughput operations for agent workflows that need to access many tools at once:

- **`batch_read_tools(registry, tool_ids, max_risk_level)`** — retrieve multiple tool records in one call, with optional risk-level filtering
- **`batch_write`** — bulk workspace writes
- **`batch_search`** — run multiple search queries and deduplicate results

Macros respect the same governance and risk-level constraints as individual tool calls.

---

## AI Agent Pipeline

MetaServer includes a **multi-agent PR validation system** that plugs into GitHub Actions. Each agent role is bound to a model via `config/models.yaml` — no code changes required to swap providers or models.

### Agents

| Agent | Role |
|-------|------|
| **Validator** | Reviews PRs for code quality, security patterns, and architectural checks |
| **Remediator** | Auto-fixes common issues (imports, conflicts, simple test failures) |
| **Architectural Guardian** | Rejects breaking changes or structural violations |
| **Functional Verifier** | Validates end-to-end functionality of meta-PRs |

### Supported Providers

Agent↔model bindings are fully configurable. MetaServer connects to any provider that exposes an **OpenAI-compatible chat completions endpoint**. The following providers are pre-configured out of the box:

| Provider | Compatibility | Examples |
|----------|--------------|---------|
| **Azure OpenAI** | OpenAI API (Azure-hosted) | GPT-4o, o4-mini, etc. |
| **OpenAI** | OpenAI API (direct) | GPT-4o, o3-mini, etc. |
| **Anthropic** | Anthropic Messages API | Claude Sonnet, Opus, etc. |
| **GitHub Models** | OpenAI-compatible (Azure inference) | DeepSeek-V3, Llama, Phi, etc. |
| **Moonshot** | OpenAI-compatible | Kimi K2, Moonshot v1, etc. |
| **OpenRouter** | OpenAI-compatible (multi-model proxy) | Any model on OpenRouter's catalog |
| **Ollama** | OpenAI-compatible (local) | Llama, Mistral, Qwen, etc. |

> **Any endpoint that implements the OpenAI `/v1/chat/completions` contract works.** To add a new provider, add its auth configuration to the `providers:` section in `config/models.yaml` and reference it in an agent binding.

### Running the Pipeline

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

## Development

### Setup

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

---

## Testing

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
| [`docs/architecture/AGENT_ARCHITECTURE_DESIGN.md`](docs/architecture/AGENT_ARCHITECTURE_DESIGN.md) | Agent runtime design, subagent architecture, LiteLLM integration |
| [`docs/architecture/SECURITY_BOUNDARY.md`](docs/architecture/SECURITY_BOUNDARY.md) | Security boundary definitions and trust model |
| [`docs/AI_AGENT_PIPELINE.md`](docs/AI_AGENT_PIPELINE.md) | AI agent pipeline for PR management |
| [`docs/AGENT_SYSTEM.md`](docs/AGENT_SYSTEM.md) | Multi-agent system for automated PR review |
| [`docs/development/CONTRIBUTING.md`](docs/development/CONTRIBUTING.md) | Contribution guidelines |
| [`docs/development/TESTING.md`](docs/development/TESTING.md) | Testing strategy and coverage |
| [`tests/SECURITY_TESTS_README.md`](tests/SECURITY_TESTS_README.md) | Security test coverage matrix |
| [`examples/ai_agent_quick_start.py`](examples/ai_agent_quick_start.py) | Quick start example for the agent pipeline |

---

## License

[License information to be added]