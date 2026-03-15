# MetaServer Code-Level Architecture Analysis

> Generated from literal source code review. Every claim references actual file paths and line numbers.
> No README or design docs were consulted — only the running codebase.

---

## 1. What Does This Server Do?

MetaServer is a **governance-aware MCP (Model Context Protocol) supervisor** that interposes between AI agents and tool execution. It wraps a set of filesystem and git tools inside a multi-layered permission, leasing, and audit system so that an AI model cannot execute sensitive operations without explicit human approval.

**Concrete evidence:**

- `src/meta_mcp/supervisor.py:269-271` — The single FastMCP instance is created with `GovernanceMiddleware` as its only middleware:
  ```python
  mcp = FastMCP(name=SERVER_NAME, middleware=[GovernanceMiddleware()], lifespan=lifespan)
  ```
- `servers/core_tools.py` — Exposes 9 tools: `read_file`, `write_file`, `delete_file`, `list_directory`, `create_directory`, `remove_directory`, `move_file`, `git_commit`, `git_push`.
- `servers/admin_tools.py` — Exposes 1 tool: `get_governance_status`.
- `config/tools.yaml:43-234` — Declares 12 tools across 2 servers (core_tools, admin_tools), plus 2 bootstrap meta-tools (`search_tools`, `get_tool_schema`).

---

## 2. How Does It Do It?

The server uses a **layered architecture** with these enforcement points:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Transport** | `supervisor.py:560-562` | HTTP/SSE via FastMCP (`mcp.run(transport="sse")`) |
| **Middleware** | `middleware.py:49-63` | `GovernanceMiddleware` intercepts every `on_call_tool` and `on_list_tools` |
| **Policy Engine** | `governance/policy.py:24-116` | Deterministic policy matrix: mode × risk → allow/block/require_approval |
| **Leasing** | `leases/manager.py:41-436` | Redis-backed ephemeral leases with TTL and call counting |
| **Tokens** | `governance/tokens.py:32-92` | HMAC-SHA256 capability tokens bound to (client, tool, expiry) |
| **Approval** | `governance/approval.py:78-116` | Pluggable approval providers (DBus GUI, FastMCP elicit, systemd-ask-password) |
| **Hooks** | `hooks/manager.py:21-413` | Agent-specific gates (tool allowlist, path fence, budget) |
| **Audit** | `audit.py:41-438` | JSON Lines structured audit trail of every governance decision |
| **Schemas** | `schemas/minimizer.py:22-96` | Progressive schema delivery (strip descriptions to 15–50 tokens) |
| **TOON** | `toon/encoder.py:11-94` | Output compression replacing large arrays with `{__toon, count, sample}` |

**Startup sequence** (`supervisor.py:158-267`):
1. Redis health check with graceful degradation to PERMISSION mode
2. Session key generation and persistence
3. Tool registry loaded from `config/tools.yaml`
4. Workspace directory creation
5. Compliance validations (bootstrap tools, no auto-mounts)
6. Approval provider health check
7. Artifact generator initialization

---

## 3. How Does It Create a Permission?

Permissions are created through a **multi-step pipeline** triggered when a model calls `get_tool_schema()`:

### Step 1: Policy Evaluation
`supervisor.py:372-399` — Before exposing any tool, the policy engine evaluates:

```python
policy_decision = evaluate_policy(
    mode=current_mode,
    tool_risk=risk_level,
    tool_id=tool_name,
)
```

The policy matrix (`governance/policy.py:33-39`):
```
┌──────────────┬─────────┬───────────┬───────────┐
│ Mode         │ Safe    │ Sensitive │ Dangerous │
├──────────────┼─────────┼───────────┼───────────┤
│ READ_ONLY    │ Allow   │ Block     │ Block     │
│ PERMISSION   │ Allow   │ Approval  │ Approval  │
│ BYPASS       │ Allow   │ Allow     │ Allow     │
└──────────────┴─────────┴───────────┴───────────┘
```

### Step 2: Capability Token Generation
`supervisor.py:427-433` — An HMAC-SHA256 signed token is generated:

```python
capability_token = generate_token(
    client_id=client_id,
    tool_id=tool_name,
    ttl_seconds=ttl_seconds,
    secret=Config.HMAC_SECRET,
)
```

Token format (`governance/tokens.py:42-43`): `base64(canonical_json_payload).hmac_sha256_hex`

### Step 3: Lease Grant
`supervisor.py:436-443` — A lease is stored in Redis:

```python
lease = await lease_manager.grant(
    client_id=client_id,
    tool_id=tool_name,
    ttl_seconds=ttl_seconds,
    calls_remaining=calls_remaining,
    mode_at_issue=current_mode.value,
    capability_token=capability_token,
)
```

Lease parameters are risk-based (`config.py:150-155`):
- Safe: 300s TTL, 3 calls
- Sensitive: 300s TTL, 1 call
- Dangerous: 120s TTL, 1 call

### Step 4: Redis Storage
`leases/manager.py:148-150` — The lease is serialized to JSON and stored with Redis `SETEX`:

```python
await redis.setex(key, ttl_seconds, lease_json)
```

Key format: `lease:{client_id}:{tool_id}` — scoped to the specific session and tool.

---

## 4. How Does It Enforce the Permission?

Enforcement happens in `GovernanceMiddleware.on_call_tool()` (`middleware.py:624-854`), which runs **on every tool invocation**:

### Lease Validation (`middleware.py:656-670`)
```python
lease = await lease_manager.validate(client_id, tool_name)
if lease is None:
    raise ToolError(
        f"No valid lease for tool '{tool_name}'. "
        f"Please request tool schema first via get_tool_schema('{tool_name}')."
    )
```

Validation checks (`leases/manager.py:169-232`):
1. Client ID is not empty
2. Lease key exists in Redis
3. Lease is not expired (`ToolLease.is_expired()`)
4. Calls remaining > 0 (`ToolLease.can_consume()`)

### Token Verification (`middleware.py:672-694`)
```python
if lease.capability_token:
    token_valid = verify_token(
        token=lease.capability_token,
        client_id=client_id,
        tool_id=tool_name,
        secret=Config.HMAC_SECRET,
    )
    if not token_valid:
        await lease_manager.revoke(client_id, tool_name)
        raise ToolError("Access denied: Invalid capability token. Lease has been revoked.")
```

### Governance Mode Enforcement (`middleware.py:759-854`)
Four enforcement paths:

| Path | Mode | Sensitive? | Action |
|------|------|------------|--------|
| 1 | BYPASS | any | Log warning, audit, execute |
| 2 | any | no | Pass through directly |
| 3 | READ_ONLY | yes | Block with `ToolError` |
| 4 | PERMISSION | yes | Check elevation → elicit → grant/deny |

### Lease Consumption (`middleware.py:731-746`)
After successful execution, the lease is atomically consumed via a Lua script (`leases/manager.py:14-38`):

```lua
calls_remaining = calls_remaining - 1
if calls_remaining <= 0 then
    redis.call("DEL", key)
end
```

This ensures a lease **cannot be double-spent** even under concurrent access.

---

## 5. How Does It Protect the Legitimacy of the Permission?

### 5a. HMAC-SHA256 Capability Tokens (`governance/tokens.py:95-209`)

Token verification performs 7 checks:
1. **Format check** — exactly 2 dot-separated parts (line 138)
2. **Canonical base64** — re-encodes and compares to reject padding variants (lines 145-149)
3. **Canonical JSON** — RFC 8785 (sorted keys, no whitespace) prevents payload manipulation (lines 153-157)
4. **HMAC signature** — constant-time `hmac.compare_digest()` prevents timing attacks (line 166)
5. **Expiration** — rejects tokens past `exp` timestamp (lines 171-174)
6. **Client binding** — `client_id` must match session (lines 177-183)
7. **Tool binding** — `tool_id` must match requested tool (lines 185-190)

### 5b. Session Key for Governance Mode Changes (`governance/session_key.py`)

Changing the governance mode requires a **one-time-use cryptographic session key**:

- Generated at startup with `secrets.token_hex(32)` — 64 hex chars (line 29)
- Written to disk with `chmod 0o400` (read-only by owner) (line 38)
- Only the SHA-256 hash is stored in Redis (line 46)
- After use, the key is **rotated** — a new key replaces it (lines 49-65)
- Validated with `hmac.compare_digest()` for constant-time comparison (line 54)

This means: you cannot change governance mode without physical access to the key file, and each key works only once.

### 5c. Scoped Elevation Hashing (`state.py:190-195`)

Elevation grants are keyed by `SHA256(tool_name:context_key:session_id)`:

```python
composite = f"{tool_name}:{context_key}:{session_id}"
hash_digest = hashlib.sha256(composite.encode("utf-8")).hexdigest()
return f"{ELEVATION_PREFIX}{hash_digest}"
```

Elevations are stored in Redis with mandatory TTL (`state.py:197-213`), ensuring they **automatically expire**.

### 5d. Context Pack Signatures (`rag/context_pack/validator.py:206-230`)

RAG context packs are HMAC-SHA256 signed with canonical JSON representation and verified with constant-time comparison, preventing tampered context from being injected.

### 5e. Fail-Closed Design

Every error path defaults to **denial**:
- Redis connection failure → PERMISSION mode (`state.py:125-138`)
- Unknown governance mode → deny (`middleware.py:846-854`)
- Approval timeout → deny (`middleware.py:479-491`)
- Approval error → deny (`middleware.py:493-507`)
- Unknown approval decision → deny (`middleware.py:594-607`)
- Token verification exception → deny (`governance/tokens.py:204-209`)
- Empty client_id → deny (`leases/manager.py:120-122`)

---

## 6. What Happens If You Don't Have Permission?

### No Lease → ToolError
`middleware.py:667-670`:
```python
raise ToolError(
    f"No valid lease for tool '{tool_name}'. "
    f"Please request tool schema first via get_tool_schema('{tool_name}')."
)
```

### Invalid Token → Lease Revoked + ToolError
`middleware.py:688-692`:
```python
await lease_manager.revoke(client_id, tool_name)
raise ToolError(
    f"Access to '{tool_name}' denied: Invalid capability token. "
    f"Lease has been revoked for security."
)
```

### READ_ONLY Mode + Sensitive Tool → ToolError
`middleware.py:791`:
```python
raise ToolError(f"Operation '{tool_name}' blocked: System is in READ_ONLY mode")
```

### PERMISSION Mode + Denied Approval → ToolError
`middleware.py:844`:
```python
raise ToolError(f"Operation '{tool_name}' denied: User did not approve")
```

### Policy Blocks Schema Access → ToolError
`supervisor.py:386-388`:
```python
raise ToolError(f"Access to '{tool_name}' blocked by policy: {policy_decision.reason}")
```

### Agent Hook Violation → ToolError with Machine-Readable Details
`middleware.py:719-722`:
```python
raise ToolError(
    f"Policy violation: {violation.reason}",
    details=violation.to_dict(),
)
```

### Schema Leakage Prevention
`tests/test_schema_leakage.py:1-14` — Blocked tools **never expose their schemas**. The schema is only returned after a lease is successfully granted, preventing attackers from probing tool capabilities without authorization.

### Audit Trail
Every denial is recorded in the JSON Lines audit log with event types:
- `blocked_read_only` (`audit.py:37`)
- `approval_denied` (`audit.py:27`)
- `approval_timeout` (`audit.py:28`)

---

## 7. What Do the Hooks Do?

The hook system (`hooks/`) provides **agent-specific policy enforcement** layered on top of the base governance system. It is **opt-in only** — hooks run exclusively when `config/agents.yaml` defines agent bindings.

### Hook Stages (`hooks/models.py:9-14`)

Three lifecycle stages:
1. **`BEFORE_TOOL_CALL`** — Pre-execution gates and custom hooks
2. **`AFTER_TOOL_RESULT`** — Post-execution receipt finalization
3. **`ON_ERROR`** — Error handling and receipt recording

### Gate System (`hooks/gates.py`)

Three built-in gates run in sequence during `BEFORE_TOOL_CALL`:

| Gate | Type | What It Checks |
|------|------|----------------|
| `ToolAllowlistGate` | `TOOL_ALLOWLIST` | Is tool in agent's `allowed_tools` list? (lines 39-72) |
| `PathFenceGate` | `PATH_FENCE` | Are file paths within `allowed_paths` / not in `denied_paths`? Auto-discovers file tools from registry by `filesystem:*` scopes (lines 75-279) |
| `BudgetGate` | `BUDGET_LIMIT` | Is agent within `max_tool_calls` global limit and per-tool limits? (lines 282-321) |

**Gate execution** (`hooks/manager.py:283-289`):
```python
for gate in self._gates:
    violation = gate.check(ctx, tool_name, arguments)
    if violation:
        receipt.finalize(success=False, error=str(violation))
        ctx.add_receipt(receipt)
        return violation, receipt
```

If any gate returns a `PolicyViolation`, the tool call is blocked immediately.

### Agent Binding Model (`hooks/models.py:60-94`)

Each agent binding defines:
- `agent_id`, `role_id`, `model_id` — identity
- `allowed_tools` / `denied_tools` — tool allowlist/denylist
- `allowed_paths` / `denied_paths` — filesystem fence with glob patterns
- `max_tool_calls` — global budget (default: 100)
- `max_tool_calls_per_tool` — per-tool budget limits

### Tool Receipts (`hooks/models.py:98-147`)

Every tool call in agent mode generates a `ToolReceipt` with:
- Start/end timestamps, duration in milliseconds
- Success/failure status with error messages
- Argument summaries and result summaries
- List of hooks applied

### Custom Hook Registration (`hooks/manager.py:235-245`)

```python
def register_hook(self, stage: HookStage, hook: Callable) -> None:
def unregister_hook(self, stage: HookStage, hook: Callable) -> bool:
```

Custom hooks can be registered at any stage. They receive `(ctx, tool_name, arguments)` and can return `PolicyViolation` to block execution.

### Agent Detection (`agent_detector.py:12-50`)

Agent ID is extracted via 4 strategies in priority order:
1. `ctx.metadata["agent_id"]`
2. `ctx.request_context.agent_id`
3. `MCP_AGENT_ID` environment variable
4. Future: Redis session mapping (stub)

---

## 8. What Mechanisms Are Involved in Context Minimization?

MetaServer employs **five distinct mechanisms** to reduce the amount of context (tokens) consumed by the AI model:

### 8a. Progressive Discovery (`supervisor.py:107-150, 274-291`)

Tools are **NOT auto-exposed** at startup. The `mount()` calls are explicitly disabled:
```python
# DEPRECATED: Auto-exposure via mount() - DO NOT UNCOMMENT
# mcp.mount(core_server)   # Would expose all 10 core tools immediately
```

Only 2 bootstrap tools are available initially: `search_tools` and `get_tool_schema`. The model must explicitly discover and request access to each tool. This reduces the initial `tools/list` response from 13+ tools to just 2, an **86.7% context reduction** (`(15-2)/15`).

### 8b. Tool Visibility Filtering (`middleware.py:270-305`)

The `on_list_tools()` middleware hook filters which tools appear in `tools/list`:

```python
async def on_list_tools(self, tools: list[str], ctx: Context) -> list[str]:
    bootstrap_tools = set(tool_registry.get_bootstrap_tools()) | {"expand_tool_schema"}
    visible_tools = [tool for tool in tools if tool in bootstrap_tools]
    # Only add tools with active leases
    for tool_name in tools:
        lease = await lease_manager.validate(client_id, tool_name)
        if lease is not None:
            visible_tools.append(tool_name)
    return visible_tools
```

A tool only appears if:
1. It's a bootstrap meta-tool, OR
2. The client has an active lease for it

### 8c. Schema Minimization (`schemas/minimizer.py:22-96`)

Full schemas are stripped to 15–50 tokens by removing:
- Descriptions
- Examples
- Default values
- Title, format metadata

Only preserved: property names, types, required arrays, enum values, nested structure.

```python
# Input (full):  {"type":"object","properties":{"file_path":{"type":"string","description":"Path to the file"}}}
# Output (mini): {"type":"object","properties":{"file_path":{"type":"string"}},"required":["file_path"]}
```

Progressive delivery controlled by `Config.ENABLE_PROGRESSIVE_SCHEMAS` (`config.py:181`), currently `False`.

### 8d. Schema Expansion on Demand (`schemas/expander.py:15-62`)

The model can request full schemas via `get_tool_schema(tool_name, expand=True)` (`supervisor.py:472-478`). Full schemas are only delivered when explicitly requested, keeping the default minimal.

### 8e. TOON Output Compression (`toon/encoder.py:11-94`)

Tool outputs are compressed by replacing arrays exceeding a threshold with metadata:
```python
# Input:  {"files": ["a", "b", "c", "d", "e", "f"]}
# Output: {"files": {"__toon": true, "count": 6, "sample": ["a", "b", "c"]}}
```

Applied in middleware (`middleware.py:66-84`):
```python
if not Config.ENABLE_TOON_OUTPUTS:
    return result
return encode_output(result, threshold=Config.TOON_ARRAY_THRESHOLD)
```

Default threshold: 5 items (`config.py:174`). This is **enabled by default**.

### 8f. Search Result Stripping (`discovery_utils.py:25-54`)

Search results return **only**:
- Tool name
- One-sentence description
- Sensitivity flag (`[SAFE]` / `[SENSITIVE]`)

Explicitly excluded: arguments, schemas, examples, usage hints, recommendations. Enforced in `supervisor.py:300-327`:

```python
def search_tools(query: str) -> str:
    results = tool_registry.search(query)
    return format_search_results(results)  # metadata only
```

---

## 9. How Are Tools Exposed Through the Server?

### Registration (Startup)
`registry/registry.py:52-98` — All tools are loaded from `config/tools.yaml` into a static `ToolRegistry` singleton:

```python
tool_registry = ToolRegistry.from_yaml(_default_tools_path)
```

Tools exist in the registry but are **NOT exposed** to MCP clients at this point.

### Bootstrap Exposure (Startup)
`supervisor.py:299, 330` — Only 2 tools are exposed via `@mcp.tool()` decorators:
1. `search_tools()` — keyword/semantic search
2. `get_tool_schema()` — schema retrieval + tool exposure trigger

### Dynamic Exposure (On Demand)
`supervisor.py:107-150` — When `get_tool_schema()` is called:

1. **Retrieve FunctionTool** from `core_server` or `admin_server` (`supervisor.py:54-104`)
2. **Register with supervisor** via `mcp.add_tool(tool_instance)` (`supervisor.py:144`)
3. **Track exposure** in `_loaded_tools` set (`supervisor.py:145`)
4. **Grant lease** before returning schema (`supervisor.py:436-443`)

After exposure, the tool appears in `tools/list` (subject to lease visibility filtering).

### Tool Mapping (`supervisor.py:73-87`)
```python
core_tools = {"read_file", "write_file", "delete_file", "list_directory",
              "create_directory", "remove_directory", "move_file", "git_commit", "git_push"}
admin_tools = {"get_governance_status"}
```

---

## 10. How Are Schemas Exposed?

### Minimal Schema (Default)
`supervisor.py:479-491` — When `ENABLE_PROGRESSIVE_SCHEMAS` is True:

```python
from .schemas import minimize_schema
tool_record.schema_full = input_schema
tool_record.schema_min = minimize_schema(input_schema)
input_schema = tool_record.schema_min
```

### Full Schema (On Request)
`supervisor.py:472-478` — When `expand=True`:

```python
if expand:
    tool_record = tool_registry.get(tool_name)
    if tool_record and tool_record.schema_full:
        input_schema = tool_record.schema_full
```

### Schema Leakage Prevention
- Blocked tools → `ToolError`, no schema returned (`supervisor.py:381-388`)
- Approval-required tools → `ToolError`, no schema returned (`supervisor.py:390-399`)
- Schema only returned after **successful lease grant** (`supervisor.py:445-501`)

### Return Format
`supervisor.py:494-501`:
```json
{
  "name": "tool_name",
  "description": "Tool description",
  "inputSchema": { ... }
}
```

---

## 11. What's Still Left to Do?

### Feature Flags Showing Incomplete Phases (`config.py:179-182`)

| Flag | Status | Phase |
|------|--------|-------|
| `ENABLE_SEMANTIC_RETRIEVAL` | `False` | Phase 2 — TF-IDF retrieval implemented (`retrieval/`) but disabled |
| `ENABLE_LEASE_MANAGEMENT` | `True` ✓ | Phase 3 — Fully implemented and active |
| `ENABLE_PROGRESSIVE_SCHEMAS` | `False` | Phase 5 — Minimizer/expander implemented but disabled |
| `ENABLE_TOON_OUTPUTS` | `True` ✓ | Phase 6 — Fully implemented and active |
| `ENABLE_MACROS` | `True` ✓ | Phase 7 — Batch operations implemented |

### Stub Functions

| Function | File | Purpose |
|----------|------|---------|
| `get_agent_id_for_session()` | `agent_detector.py:53-67` | Redis-backed session→agent mapping — returns `None` |
| `set_agent_id_for_session()` | `agent_detector.py:70-86` | Redis-backed session→agent mapping — returns `False` |
| `validate_no_auto_mounts()` | `validation.py:82-99` | Auto-mount detection — always returns `True` |

### Phase 8: MCP Client Notifications

`leases/manager.py:393-422` — The `_emit_list_changed()` infrastructure exists (called on grant, consume, revoke, purge) but **no callbacks are ever registered**. The method iterates over an empty list, making it a no-op. This needs actual MCP protocol `notifications/tools/list_changed` integration.

### RAG Pipeline Not Connected to Main Server

The full RAG system exists (`src/meta_mcp/rag/`) with:
- Document ingestion with PDF/DOCX/text extractors
- Chunking and embedding (Gemini, OpenAI adapters)
- Qdrant vector storage
- BM25 + semantic hybrid retrieval
- LLM-based explainer for chunk selection
- HMAC-signed context packs

However, this is **not wired into the supervisor or any tool**. No tool exposes RAG functionality to clients. The embedding provider requires API keys (`config.py:94-101`) that default to empty strings.

### Governance Mode Change Tool Not Exposed

`state.py:146-188` — `set_mode()` exists with full session key validation and rotation, but **no tool** in the supervisor exposes this functionality. Mode changes require direct Redis access or a separate admin interface.

### Approval Provider Fallback Chain Incomplete

`governance/approval.py:1-7` documents three providers:
1. DBus GUI (GNOME Shell extension)
2. FastMCP `ctx.elicit` (client-side prompts)
3. `systemd-ask-password` (terminal fallback)

Only the FastMCP elicit provider is fully implemented. DBus and systemd providers exist but are environment-dependent.

### Config Validation for Production

`config.py:160-162` — The HMAC secret defaults to a known dev value:
```python
HMAC_SECRET: str = os.getenv(
    "HMAC_SECRET", "default_dev_secret_change_in_production_32bytes_minimum"
)
```

While `Config.validate()` warns about this, it only **errors** when `ENVIRONMENT=production`. The default is insecure for any deployment.

### Semantic Search Feature Flag

The lightweight TF-IDF semantic search in `retrieval/` is complete and tested but disabled behind `ENABLE_SEMANTIC_RETRIEVAL = False`. The full RAG semantic search in `rag/retrieval/` is a separate, more advanced system also not activated.

---

## Appendix: Security Invariants Summary

| Invariant | Location | Mechanism |
|-----------|----------|-----------|
| Fail-closed on Redis failure | `state.py:125-138` | Defaults to PERMISSION mode |
| Fail-closed on unknown mode | `middleware.py:846-854` | Denies with ToolError |
| Fail-closed on approval error | `middleware.py:609-622` | Returns `(False, 0, [])` |
| Constant-time token comparison | `governance/tokens.py:166` | `hmac.compare_digest()` |
| Constant-time key comparison | `governance/session_key.py:54` | `hmac.compare_digest()` |
| Canonical JSON encoding | `governance/tokens.py:13-29` | RFC 8785 prevents payload manipulation |
| One-time-use session keys | `governance/session_key.py:49-65` | Key rotated after every use |
| Atomic lease consumption | `leases/manager.py:14-38` | Redis Lua script prevents double-spend |
| Path traversal prevention | `governance/artifacts.py:44-99` | Resolved path must be under artifacts_root |
| Schema leakage prevention | `supervisor.py:381-399` | Blocked/approval-required tools get no schema |
| Session-scoped leases | `leases/manager.py:77-88` | Key format `lease:{client_id}:{tool_id}` |
| HTML escaping in artifacts | `governance/artifacts.py:296-298` | `html.escape()` on all user inputs |
| Empty client_id rejection | `leases/manager.py:120-122` | Prevents cross-session access |
| Workspace path validation | `servers/core_tools.py` | All paths validated against WORKSPACE_ROOT |
| Mandatory elevation TTL | `state.py:199-200` | `ttl <= 0` → `return False` |
