# Code-First Repository Audit: MetaServer

**Audit Date:** 2026-03-15
**Methodology:** Forensic code inspection only — no documentation, README, or prose claims used as evidence.

---

## 1. Executive Reality Check

MetaServer is a **functioning FastMCP-based tool governance server** that implements a tri-state permission model (READ_ONLY / PERMISSION / BYPASS) for controlling AI agent access to filesystem and git operations. The server is operational with the following actually-implemented capabilities:

- **Progressive tool discovery**: Only 2 bootstrap tools are auto-exposed; all other tools are exposed on-demand via `get_tool_schema()`
- **Tri-state governance middleware**: Every tool call passes through `GovernanceMiddleware.on_call_tool()`, which enforces READ_ONLY blocking, PERMISSION-mode elicitation, or BYPASS passthrough
- **Redis-backed lease management**: Tools require leases (granted during schema retrieval) to be invoked
- **HMAC-SHA256 capability tokens**: Tokens are generated at lease grant time and verified at tool invocation
- **Scoped elevation with TTL**: Approved sensitive operations get time-limited elevation cached in Redis
- **Multi-provider approval system**: DBus GUI, FastMCP elicit, and systemd-ask-password providers with auto-selection
- **Agent hook system**: Opt-in gates (tool allowlist, path fence, budget limit) for agent-specific policy enforcement
- **TOON output compression**: Large arrays in tool outputs are replaced with metadata summaries
- **Structured audit logging**: JSON Lines audit trail with buffered writes and rotation

**What is NOT implemented despite types/stubs existing:**
- Semantic retrieval search (feature-flagged off: `ENABLE_SEMANTIC_RETRIEVAL = False`)
- Progressive schema minimization (feature-flagged off: `ENABLE_PROGRESSIVE_SCHEMAS = False`)
- Redis-backed session→agent mapping (stub functions return `None`/`False`)
- Full RAG pipeline (code exists but is not wired into the server runtime)

---

## 2. Runtime Architecture from Code

### Entrypoints

| Entrypoint | File | Function |
|---|---|---|
| Module execution | `src/meta_mcp/__main__.py:11` | Calls `main()` from supervisor |
| Server startup | `src/meta_mcp/supervisor.py:518` | `main()` — configures logging, validates config, runs SSE server |
| FastMCP server | `src/meta_mcp/supervisor.py:271` | `mcp = FastMCP(name="MetaSupervisor", middleware=[GovernanceMiddleware()], lifespan=lifespan)` |

### Main Modules

| Module | Path | Purpose |
|---|---|---|
| Supervisor | `src/meta_mcp/supervisor.py` | FastMCP server with bootstrap tools and lifecycle |
| Middleware | `src/meta_mcp/middleware.py` | GovernanceMiddleware — all enforcement happens here |
| State | `src/meta_mcp/state.py` | Redis-backed tri-state mode + elevation cache |
| Config | `src/meta_mcp/config.py` | Centralized env-var-driven configuration |
| Audit | `src/meta_mcp/audit.py` | Structured JSON Lines audit logger |
| Policy | `src/meta_mcp/governance/policy.py` | Deterministic policy matrix evaluation |
| Tokens | `src/meta_mcp/governance/tokens.py` | HMAC-SHA256 token generation/verification |
| Approval | `src/meta_mcp/governance/approval.py` | Multi-provider approval system |
| Artifacts | `src/meta_mcp/governance/artifacts.py` | HTML/JSON artifact generation for approvals |
| Session Key | `src/meta_mcp/governance/session_key.py` | One-time-use key for mode changes |
| Leases | `src/meta_mcp/leases/manager.py` | Redis-backed lease management with Lua consume |
| Hooks | `src/meta_mcp/hooks/manager.py` | Agent hook orchestrator |
| Gates | `src/meta_mcp/hooks/gates.py` | ToolAllowlist, PathFence, Budget gates |
| Registry | `src/meta_mcp/registry/registry.py` | YAML-loaded static tool registry |
| TOON | `src/meta_mcp/toon/encoder.py` | Array compression encoder |
| Schemas | `src/meta_mcp/schemas/minimizer.py` | Schema minimization (feature-flagged off) |
| Core Tools | `servers/core_tools.py` | File/directory/git operations (FastMCP server) |
| Admin Tools | `servers/admin_tools.py` | Governance status query tool |

### Execution Flow (Request Lifecycle)

1. **Server starts** via `main()` → `mcp.run(transport="sse", host=HOST, port=PORT)` (supervisor.py:562)
2. **Lifespan startup** (supervisor.py:159-267):
   - Redis health check with graceful degradation to PERMISSION mode
   - Governance session key initialization (written to filesystem, hash stored in Redis)
   - Tool registry loaded from `config/tools.yaml`
   - Workspace directory creation
   - Compliance validation (bootstrap tools check)
   - Approval provider health check
   - Artifact generator initialization
3. **Client connects** via SSE transport
4. **Tool list request** → `GovernanceMiddleware.on_list_tools()` (middleware.py:270-305) filters to bootstrap + leased tools
5. **`search_tools(query)`** → `tool_registry.search()` → keyword matching → returns `ToolCandidate` metadata (no schemas)
6. **`get_tool_schema(tool_name)`** (supervisor.py:331-504):
   - Validates tool in registry
   - Evaluates governance policy
   - Exposes tool dynamically via `_expose_tool()` → `mcp.add_tool()`
   - Generates HMAC capability token
   - Grants Redis lease with token
   - Returns JSON schema
7. **Tool invocation** → `GovernanceMiddleware.on_call_tool()` (middleware.py:624-854):
   - **Lease validation** (if enabled): Checks Redis lease exists for client+tool
   - **Capability token verification** (if lease has token): HMAC-SHA256 verification
   - **Agent hooks** (if agent binding exists): Runs before_tool_call gates
   - **Governance mode check**:
     - BYPASS → execute immediately (with audit)
     - Non-sensitive tool → pass through
     - READ_ONLY + sensitive → block with ToolError
     - PERMISSION + sensitive → check elevation cache → elicit approval if needed
   - **Post-execution**: Consume lease, run after_tool_result hooks, apply TOON encoding

### Cross-Module Dependencies

```
supervisor.py
  ├── middleware.py (GovernanceMiddleware — registered as only middleware)
  │   ├── state.py (governance_state — get/check mode, elevation)
  │   ├── leases/manager.py (lease_manager — validate, consume, revoke)
  │   ├── governance/tokens.py (verify_token)
  │   ├── governance/approval.py (get_approval_provider → request_approval)
  │   ├── governance/artifacts.py (get_artifact_generator → generate HTML/JSON)
  │   ├── audit.py (audit_logger — all events logged)
  │   ├── hooks/manager.py (hook_manager — agent hooks)
  │   ├── agent_detector.py (detect_agent_id)
  │   ├── toon/encoder.py (encode_output)
  │   └── registry/registry.py (tool_registry — scopes, metadata)
  ├── servers/core_tools.py (core_server — file/git tools)
  ├── servers/admin_tools.py (admin_server — governance status)
  └── config.py (Config — all env-var-driven settings)
```

---

## 3. Code-Backed Answers to Core Questions

### Q1: What does this server actually do today?

**Answer:** It provides a governed MCP (Model Context Protocol) server that controls AI agent access to filesystem and git tools through progressive discovery, lease-based access control, HMAC capability tokens, tri-state governance modes, and user-approval elicitation.

**Evidence:**
- `supervisor.py:271`: `mcp = FastMCP(name="MetaSupervisor", middleware=[GovernanceMiddleware()], lifespan=lifespan)`
- `supervisor.py:562`: `mcp.run(transport="sse", host=HOST, port=PORT)` — server runs over SSE
- `supervisor.py:299-504`: Two bootstrap tools (`search_tools`, `get_tool_schema`) are the only auto-exposed entry points
- `middleware.py:624-854`: `on_call_tool()` intercepts every tool invocation

### Q2: How does it do it, step by step?

**Answer:** See "Execution Flow" in Section 2 above. The critical step-by-step is:

1. `main()` starts SSE server (supervisor.py:518-567)
2. `lifespan()` initializes Redis, session key, registry, workspace (supervisor.py:159-267)
3. Clients discover tools via `search_tools()` → keyword search (supervisor.py:300-327)
4. Clients request schemas via `get_tool_schema()` → tool exposed + lease granted (supervisor.py:331-504)
5. Tool calls intercepted by `GovernanceMiddleware.on_call_tool()` → lease check → token verify → hooks → mode enforcement → execute → lease consume → TOON encode (middleware.py:624-854)

**Evidence:** All function references above are directly invoked in the runtime path.

### Q3: How is a permission created?

**Answer:** Permissions are created through three mechanisms:

1. **Leases**: Created in `get_tool_schema()` (supervisor.py:436-443) via `lease_manager.grant()` → stored in Redis with TTL. Lease key format: `lease:{client_id}:{tool_id}`.

2. **Capability tokens**: Generated at lease grant time via `generate_token()` (tokens.py:32-92) — HMAC-SHA256 signed with `{client_id, tool_id, exp, iat, context_key}` payload.

3. **Scoped elevations**: Created when user approves a sensitive operation in PERMISSION mode (middleware.py:823-825) via `_grant_elevation()` → stored in Redis with TTL. Elevation key format: `elevation:{SHA256(tool_name:context_key:session_id)}`.

**Evidence:**
- `supervisor.py:427-443`: Token generation + lease grant in `get_tool_schema()`
- `middleware.py:159-193`: `_grant_elevation()` stores elevation in Redis
- `state.py:197-213`: `grant_elevation()` uses `redis.setex(hash_key, ttl, "granted")`

### Q4: How is that permission enforced?

**Answer:** Enforcement happens in `GovernanceMiddleware.on_call_tool()` (middleware.py:624-854):

1. **Lease enforcement** (middleware.py:656-694): `lease_manager.validate(client_id, tool_name)` — returns None if no valid lease exists → raises `ToolError`. Token verified via `verify_token()`.

2. **Mode enforcement** (middleware.py:748-854):
   - BYPASS: Execute immediately
   - Non-sensitive: Pass through
   - READ_ONLY + sensitive: Raise `ToolError("blocked: System is in READ_ONLY mode")`
   - PERMISSION + sensitive: Check `_check_elevation()` → if none, `_elicit_approval()` → if denied, raise `ToolError`

3. **Hook enforcement** (middleware.py:700-722): If agent binding exists, `hook_manager.run_before_tool_call()` runs gates. If any gate returns `PolicyViolation`, raises `ToolError`.

4. **Tool list filtering** (middleware.py:270-305): `on_list_tools()` filters to only bootstrap + leased tools.

**Evidence:** All enforcement paths terminate in either `call_next()` (success) or `raise ToolError(...)` (denial). There is no bypass path that skips all checks.

### Q5: How is permission legitimacy/integrity protected?

**Answer:**

1. **Capability tokens**: HMAC-SHA256 with constant-time comparison (`hmac.compare_digest` at tokens.py:166). Tokens are bound to `client_id + tool_id + expiration`. Non-canonical base64 encoding is rejected (tokens.py:147-149). Non-canonical JSON payload rejected (tokens.py:155-157).

2. **Governance session key**: Used to authenticate mode changes. Key is generated with `secrets.token_hex(32)` (session_key.py:29), written to filesystem with mode 0o400 (session_key.py:38), hash stored in Redis (session_key.py:46). Validated with `hmac.compare_digest` (session_key.py:54). **Key rotates after each use** (session_key.py:58-60).

3. **Elevation keys**: SHA256 hashed composite of `{tool_name}:{context_key}:{session_id}` (state.py:191-195). Stored in Redis with mandatory TTL (state.py:197-213 — `ttl <= 0` is rejected).

4. **Lease isolation**: Keys scoped to `lease:{client_id}:{tool_id}` — cross-session access prevented by client_id validation. Empty client_id rejected (manager.py:120-121).

**Evidence:**
- `tokens.py:160-166`: HMAC verification with `hmac.compare_digest`
- `session_key.py:49-65`: Key validation with `hmac.compare_digest` + rotation
- `state.py:199-200`: TTL validation rejects `ttl <= 0`
- `leases/manager.py:120-121`: Empty client_id check in `grant()`

### Q6: What happens when permission is missing, invalid, expired, bypassed, or malformed?

**Answer:** All failure paths are fail-closed (deny):

| Scenario | Code Path | Result |
|---|---|---|
| No lease | middleware.py:662-670 | `ToolError("No valid lease...")` |
| Invalid token | middleware.py:682-692 | Token revoked + `ToolError("Invalid capability token")` |
| Expired lease | leases/manager.py:211-213 | `validate()` returns None → treated as no lease |
| READ_ONLY + sensitive | middleware.py:783-791 | `ToolError("blocked: READ_ONLY mode")` |
| PERMISSION + no elevation + denied | middleware.py:843-844 | `ToolError("denied: User did not approve")` |
| Elicitation timeout | middleware.py:479-491 | Returns `(False, 0, [])` → denial |
| Elicitation error | middleware.py:609-622 | Returns `(False, 0, [])` → denial |
| Unknown mode | middleware.py:846-854 | `ToolError("denied: Unknown governance mode")` |
| No scopes selected on approval | middleware.py:526-539 | Returns `(False, 0, [])` → denial |
| Missing required scopes | middleware.py:543-557 | Returns `(False, 0, [])` → denial |
| Invalid extra scopes | middleware.py:560-574 | Returns `(False, 0, [])` → denial |
| Redis connection failure in get_mode | state.py:125-138 | Falls back to `ExecutionMode.PERMISSION` |
| Invalid governance session key | state.py:162-169 | `PermissionError("Invalid governance session key")` |
| Agent gate violation | middleware.py:708-722 | `ToolError("Policy violation: ...")` |

**Evidence:** Every failure path terminates in `ToolError`, `PermissionError`, or denial return value. No silent failures that allow execution.

### Q7: What do the hooks do?

**Answer:** Hooks provide an agent-specific policy layer with three gate types:

1. **ToolAllowlistGate** (gates.py:39-72): Checks if tool is in agent's allowed_tools list (or not in denied_tools). Returns `PolicyViolation` if blocked.

2. **PathFenceGate** (gates.py:75-279): Auto-discovers file tools from registry (by `filesystem:*` scopes). Checks file path arguments against agent's allowed_paths/denied_paths patterns (fnmatch glob). Returns `PolicyViolation` if path is outside fence.

3. **BudgetGate** (gates.py:282-321): Enforces global tool call limit (`max_tool_calls`) and per-tool limits (`max_tool_calls_per_tool`). Returns `PolicyViolation` if budget exceeded.

**Evidence:**
- `gates.py:329`: `DEFAULT_GATES = [tool_allowlist_gate, path_fence_gate, budget_gate]`
- `manager.py:284-289`: Gates run in sequence in `run_before_tool_call()`
- `manager.py:304`: `ctx.increment_tool_call(tool_name)` — budget consumed BEFORE execution

### Q8: Where do hooks run in the lifecycle?

**Answer:** Hooks run inside `GovernanceMiddleware.on_call_tool()`, AFTER lease/token validation and BEFORE mode enforcement:

```
on_call_tool() {
  1. Lease validation (middleware.py:656-694)
  2. Token verification (middleware.py:672-694)
  3. AGENT HOOKS: run_before_tool_call() (middleware.py:700-722)  ← HERE
  4. Mode check + governance enforcement (middleware.py:748-854)
  5. Tool execution (call_next())
  6. Lease consumption (middleware.py:731-746)
  7. AGENT HOOKS: run_after_tool_result() (middleware.py:724-729)  ← HERE
  8. TOON encoding (middleware.py:772, 780, 812, 841)
}
```

**Evidence:**
- `middleware.py:700-722`: `run_before_tool_call()` invoked before mode check
- `middleware.py:724-729`: `_run_after_hooks(result)` called after execution
- `middleware.py:771, 779, 811, 840`: `_run_after_hooks` called in each success path

### Q9: What mechanisms are used for context minimization?

**Answer:** Three operational mechanisms:

1. **Progressive discovery** (supervisor.py:107-150): Tools are NOT auto-mounted. `mcp.mount()` calls are explicitly commented out (supervisor.py:289-291). Tools are exposed one-at-a-time via `_expose_tool()` → `mcp.add_tool()` only when `get_tool_schema()` is called.

2. **Tool list filtering** (middleware.py:270-305): `on_list_tools()` returns only bootstrap tools + tools with active leases for this client. All others are hidden.

3. **Search results strip schemas** (discovery_utils.py:25-54): `format_search_results()` returns only tool_id, description_1line, and risk_level. No argument schemas, examples, or usage hints.

4. **TOON output compression** (toon/encoder.py:11-94): Arrays exceeding threshold (default 5) are replaced with `{"__toon": true, "count": N, "sample": [first 3]}`. Applied to all tool outputs when `ENABLE_TOON_OUTPUTS=True` (default).

5. **Schema minimization** (schemas/minimizer.py): Code exists to strip descriptions, examples, defaults from schemas. However, it is **feature-flagged off** (`ENABLE_PROGRESSIVE_SCHEMAS = False` in config.py:181). The `expand` parameter on `get_tool_schema()` does function but the minimize path only activates when the flag is on.

**Evidence:**
- `supervisor.py:289-291`: `# DEPRECATED: Auto-exposure via mount() - DO NOT UNCOMMENT`
- `supervisor.py:121-122`: `if tool_name in _loaded_tools: return True` (skip if already exposed)
- `middleware.py:279-281`: `if not Config.ENABLE_LEASE_MANAGEMENT: return tools` (lease filter)
- `config.py:181`: `ENABLE_PROGRESSIVE_SCHEMAS: bool = False`

### Q10: Where is tool exposure implemented?

**Answer:** Tool exposure is implemented in `_expose_tool()` (supervisor.py:107-150):

1. Checks if already exposed via `_loaded_tools` set
2. Checks if bootstrap tool (already auto-exposed via `@mcp.tool()`)
3. Verifies tool exists in registry
4. Retrieves `FunctionTool` instance from `core_server` or `admin_server` via `_get_tool_function()` (supervisor.py:54-104)
5. Registers with FastMCP via `mcp.add_tool(tool_instance)` (supervisor.py:144)
6. Adds to `_loaded_tools` tracking set

**Evidence:**
- `supervisor.py:144`: `mcp.add_tool(tool_instance)` — the actual exposure call
- `supervisor.py:73-87`: Hardcoded mapping of which tools belong to `core_server` vs `admin_server`

### Q11: How are tools registered/exposed through the server?

**Answer:**

- **Registry**: All tools defined in `config/tools.yaml` and loaded by `ToolRegistry.from_yaml()` at module import time (registry.py:264-268). Singleton `tool_registry`.
- **Bootstrap tools**: `search_tools` and `get_tool_schema` registered via `@mcp.tool()` decorators (supervisor.py:299, 331). Always visible.
- **Core/Admin tools**: Defined in `servers/core_tools.py` and `servers/admin_tools.py` as separate FastMCP servers (`core_server`, `admin_server`). NOT mounted — exposed on-demand via `_expose_tool()` → `mcp.add_tool()`.

**Evidence:**
- `config/tools.yaml`: 12 tool definitions (2 bootstrap, 9 core, 1 admin) across 2 servers
- `supervisor.py:289-291`: Mount calls commented out
- `supervisor.py:144`: Dynamic exposure via `mcp.add_tool()`

### Q12: How are schemas exposed/generated/validated?

**Answer:**

- **Schema retrieval**: `get_tool_schema()` calls `mcp.get_tool(tool_name)` → `tool.to_mcp_tool()` → extracts `inputSchema` (supervisor.py:460-469).
- **Progressive schemas**: When `ENABLE_PROGRESSIVE_SCHEMAS=True` AND `expand=False`, schemas are minimized via `minimize_schema()` (supervisor.py:479-491). Full schemas stored in `tool_record.schema_full` for later expansion. **Currently disabled**.
- **Schema expansion**: When `expand=True`, `tool_record.schema_full` is returned if available, otherwise the live tool schema (supervisor.py:472-478).
- **Validation**: `ToolRecord.validate_invariants()` checks `risk_level ∈ {safe, sensitive, dangerous}`, non-empty description, non-empty tags (models.py:77-92). `validate_minimal_schema()` exists but is not invoked at runtime.

**Evidence:**
- `supervisor.py:469`: `input_schema = mcp_tool.inputSchema`
- `config.py:181`: `ENABLE_PROGRESSIVE_SCHEMAS: bool = False`
- `schemas/minimizer.py:179-215`: `validate_minimal_schema()` — exists but not called in any runtime path

### Q13: What security boundaries actually exist in code?

**Answer:**

| Boundary | Implementation | Evidence |
|---|---|---|
| Workspace path containment | `_validate_path()` in core_tools.py:22-47 | `target.relative_to(workspace)` check |
| HMAC token integrity | `verify_token()` in tokens.py:95-209 | Constant-time `hmac.compare_digest` |
| Session key rotation | `validate_and_rotate()` in session_key.py:49-65 | One-time-use key, rotated after use |
| Lease scoping | `_lease_key()` in leases/manager.py:77-88 | `lease:{client_id}:{tool_id}` scoping |
| Empty client_id rejection | Multiple locations in leases/manager.py | `if not client_id or not client_id.strip()` |
| Artifact path traversal | `_validate_path()` in artifacts.py:103-123 | `resolved.is_relative_to(self.artifacts_root)` |
| System directory protection | `_ensure_safe_root()` in artifacts.py:44-99 | Blocklist of system paths |
| Content truncation in audit | audit.py:18 | `MAX_CONTENT_LENGTH = 1000` |
| HTML escaping in artifacts | artifacts.py:296-298 | `html.escape()` on all user input |
| Governance key file perms | session_key.py:33-38 | `os.chmod(self.key_dir, 0o700)`, `os.chmod(self.key_path, 0o400)` |
| Token expiration | tokens.py:171-173 | `if time.time() > exp` |
| Redis TTL on leases | leases/manager.py:150 | `redis.setex(key, ttl_seconds, lease_json)` |
| Redis TTL on elevations | state.py:205 | `redis.setex(hash_key, ttl, "granted")` |
| Mode change authentication | state.py:146-188 | Requires valid session key |
| HMAC secret validation | config.py:201-231 | Warns/errors on weak secrets |

### Q14: What guardrails exist only partially or not at all?

**Answer:**

| Guardrail | Status | Evidence |
|---|---|---|
| **Rate limiting** | **Missing** | No rate limiter in middleware or server. Clients can call tools at unlimited rate. |
| **Cross-tool scope escalation** | **Partial** | Scopes validated per-approval but leases are tool-scoped, not scope-scoped. Once a lease is granted, the capability token doesn't carry scope restrictions. |
| **Audit log tamper protection** | **Missing** | Audit log is a plain JSONL file with no cryptographic sealing or append-only filesystem enforcement. |
| **Session key compromise recovery** | **Partial** | Key rotates after use, but if a key is compromised before use, attacker can change governance mode once. No mechanism to invalidate a compromised key without restart. |
| **HMAC secret rotation** | **Missing** | `HMAC_SECRET` is a static env var. No runtime rotation mechanism. All tokens signed with same key for server lifetime. |
| **Lease revocation broadcast** | **Partial** | `_emit_list_changed()` calls callbacks (leases/manager.py:393-413) but no callbacks are registered in the runtime path. The notification mechanism is wired but empty. |
| **Token revocation list** | **Missing** | No CRL/blocklist for capability tokens. If a token is compromised, it remains valid until TTL expires. |
| **Input sanitization for tool arguments** | **Missing** | Tool arguments are passed directly to core tools. While path containment exists for file tools, argument values like `content` in `write_file` are not sanitized. |
| **Concurrent mode change protection** | **Partial** | Session key rotation provides some protection but no distributed lock. Two concurrent mode-change requests could theoretically race. |

### Q15: What is implemented vs stubbed vs planned but absent?

See Section 8 table below.

### Q16: What are the highest-risk gaps?

See Section 9 below.

---

## 4. Permission System Audit

### Creation

| Permission Type | Creation Point | Code |
|---|---|---|
| Lease | `get_tool_schema()` | supervisor.py:436-443 → `lease_manager.grant()` |
| Capability Token | `get_tool_schema()` | supervisor.py:427-433 → `generate_token()` |
| Elevation | `_grant_elevation()` after approval | middleware.py:159-193 → `governance_state.grant_elevation()` |
| Governance Session Key | `lifespan()` startup | supervisor.py:201 → `governance_state.initialize_session_key()` |

### Storage

| Permission Type | Storage | Key Format | TTL |
|---|---|---|---|
| Lease | Redis | `lease:{client_id}:{tool_id}` | Risk-based: safe=300s, sensitive=300s, dangerous=120s |
| Capability Token | Embedded in lease (Redis) | Inside lease JSON `capability_token` field | Same as lease |
| Elevation | Redis | `elevation:{SHA256(tool:context:session)}` | User-specified from approval (default 300s) |
| Session Key | Filesystem + Redis hash | File: `{GOVERNANCE_KEY_DIR}/governance.key`, Redis: `governance:session_key_hash` | Server lifetime |

### Propagation

- Leases are granted to a specific `client_id` (derived from `ctx.session_id`)
- Tokens are embedded in the lease and verified on each tool call
- Elevations are scoped to `(tool_name, context_key, session_id)` tuples
- Session key is written to a file readable only by the server process owner

### Enforcement

- **Lease**: Checked in `middleware.py:656-670` — `lease_manager.validate(client_id, tool_name)`
- **Token**: Verified in `middleware.py:672-694` — `verify_token(token, client_id, tool_id, secret)`
- **Elevation**: Checked in `middleware.py:796` — `_check_elevation(tool_name, arguments, session_id)`
- **Session key**: Validated in `state.py:161` — `_key_manager.validate_and_rotate(session_key, redis)`

### Verification

- **Token signature**: `hmac.compare_digest` (tokens.py:166) — constant-time comparison
- **Token expiration**: `time.time() > exp` (tokens.py:172)
- **Token binding**: `client_id`, `tool_id`, optional `context_key` all checked (tokens.py:177-199)
- **Canonical encoding**: Base64 normalization check (tokens.py:147-149), JSON canonicalization check (tokens.py:155-157)
- **Session key**: `hmac.compare_digest(provided_key, self._current_key)` (session_key.py:54)

### Failure Behavior

All permission failures are fail-closed:
- Missing lease → `ToolError` (middleware.py:667-670)
- Invalid token → lease revoked + `ToolError` (middleware.py:682-692)
- Expired lease → returns None from `validate()` (leases/manager.py:211-213)
- Redis connection failure → `ExecutionMode.PERMISSION` fallback (state.py:125-138)

### Anti-Bypass Protections

- **Bootstrap tool skip**: Only `search_tools` and `get_tool_schema` skip lease checks (middleware.py:651)
- **ENABLE_LEASE_MANAGEMENT flag**: When disabled, lease checks are fully skipped (middleware.py:653, 279-281). This is a **configurable bypass** — currently `True` by default.
- **No middleware skip**: `GovernanceMiddleware` is the only middleware registered at server creation (supervisor.py:271) and cannot be removed at runtime.
- **Fail-safe default**: Redis failures fall back to PERMISSION mode, not BYPASS (state.py:125-138).

### Missing Protections

- **No token revocation list**: Compromised tokens valid until TTL expiry
- **No rate limiting**: Unlimited lease grant/tool call rate
- **No HMAC key rotation**: Static key for server lifetime
- **No lease renewal validation**: A client could call `get_tool_schema()` repeatedly to get fresh leases without limit

---

## 5. Hooks Audit

### Where Hooks Are Defined

- **Gate definitions**: `src/meta_mcp/hooks/gates.py` — three gate classes
- **Gate defaults**: `gates.py:329`: `DEFAULT_GATES = [tool_allowlist_gate, path_fence_gate, budget_gate]`
- **Manager**: `src/meta_mcp/hooks/manager.py` — `HookManager` class
- **Singleton**: `manager.py:413`: `hook_manager = HookManager()`
- **Configuration**: Loaded from `config/agents.yaml` (if it exists)
- **Models**: `src/meta_mcp/hooks/models.py` — `AgentBinding`, `AgentRunContext`, `ToolReceipt`, `PolicyViolation`

### Where They Are Invoked

- **Before tool call**: `middleware.py:704-706` → `hook_manager.run_before_tool_call(session_id, tool_name, arguments)`
- **After tool result**: `middleware.py:726-728` → `hook_manager.run_after_tool_result(session_id, tool_name, result, hook_receipt, error)`
- **Agent detection**: `middleware.py:702` → `detect_agent_id(context)`
- **Guard check**: `middleware.py:704` → `hook_manager.is_agent_mode(agent_id)` — returns False if no binding exists

### What They Can Affect

1. **Block tool calls**: If any gate returns `PolicyViolation`, the tool call is blocked with `ToolError` (middleware.py:708-722)
2. **Track budget**: `BudgetGate` increments counters and blocks when limits exceeded (gates.py:282-321)
3. **Enforce path fencing**: `PathFenceGate` blocks file operations outside allowed paths (gates.py:75-279)
4. **Restrict tool access**: `ToolAllowlistGate` limits which tools an agent can call (gates.py:39-72)
5. **Generate receipts**: Each tool call produces a `ToolReceipt` for audit trail (models.py:98-147)

### What They Currently Enforce in Reality

**In practice, hooks are disabled by default** because:
1. `config/agents.yaml` does not exist (only `config/agents.yaml.example` exists)
2. When config file is missing, `_load_config()` returns `False` and `_enabled = False` (manager.py:84-87)
3. `is_agent_mode()` returns `False` when `_enabled is False` (manager.py:165-166)
4. Therefore, `middleware.py:704` never enters the hook block

**Hooks are fully implemented but opt-in** — they activate only when `config/agents.yaml` exists with valid agent bindings.

---

## 6. Context Minimization Audit

### Implemented Mechanisms

1. **Progressive discovery (ACTIVE)**
   - File: `supervisor.py:289-291` — `mcp.mount()` calls commented out
   - File: `supervisor.py:107-150` — `_expose_tool()` adds tools individually
   - File: `supervisor.py:414-420` — exposure happens inside `get_tool_schema()`
   - Effect: Only 2 tools visible at startup instead of 12

2. **Tool list filtering (ACTIVE when ENABLE_LEASE_MANAGEMENT=True)**
   - File: `middleware.py:270-305` — `on_list_tools()` filters
   - Effect: Client sees only bootstrap + leased tools

3. **Search result stripping (ACTIVE)**
   - File: `discovery_utils.py:25-54` — returns only name, description, risk
   - File: `registry/models.py:104-155` — `ToolCandidate` has no schema fields
   - Effect: No schema leakage during search

4. **TOON output compression (ACTIVE)**
   - File: `toon/encoder.py:11-94` — replaces arrays > threshold with summaries
   - File: `middleware.py:76-84` — applied to all tool results
   - File: `config.py:172-174` — `ENABLE_TOON_OUTPUTS=True`, `TOON_ARRAY_THRESHOLD=5`
   - Effect: Reduces token consumption for large outputs

5. **Schema minimization (EXISTS BUT DISABLED)**
   - File: `schemas/minimizer.py:22-96` — `minimize_schema()` strips descriptions/examples
   - File: `config.py:181` — `ENABLE_PROGRESSIVE_SCHEMAS: bool = False`
   - File: `supervisor.py:479-491` — minimize path gated by feature flag
   - Effect: None at runtime (flag is off)

---

## 7. Tool and Schema Exposure Audit

### How Tools Are Exposed

- **Static registry**: 12 tools defined in `config/tools.yaml`, loaded at import time into `tool_registry` singleton
- **Bootstrap auto-exposure**: 2 tools (`search_tools`, `get_tool_schema`) via `@mcp.tool()` decorators
- **Dynamic exposure**: Via `_expose_tool()` → `mcp.add_tool(tool_instance)` when `get_tool_schema()` is called
- **Tool sources**: `core_server` (9 tools: read_file, write_file, delete_file, list_directory, create_directory, move_file, remove_directory, git_commit, git_push) and `admin_server` (1 tool: get_governance_status)
- **Exposure is one-way**: Once exposed, tools remain visible for the server lifetime (no `_loaded_tools.remove()` anywhere)

### How Schemas Are Built/Exposed

- Schemas come from FastMCP's `tool.to_mcp_tool().inputSchema` (supervisor.py:466-469)
- Returned as JSON from `get_tool_schema()` (supervisor.py:494-501)
- `schema_min` and `schema_full` fields in `ToolRecord` may be populated from `config/tools.yaml` but progressive schema delivery is disabled

### Exposure Characteristics

| Aspect | Status |
|---|---|
| Static registry | Yes — `config/tools.yaml` loaded at startup |
| Dynamic exposure | Yes — `mcp.add_tool()` on demand |
| Filtered by lease | Yes — `on_list_tools()` filters when lease management enabled |
| Permission-gated | Partial — `get_tool_schema()` evaluates policy before exposure (blocks in READ_ONLY for sensitive tools) |
| Schema stripping | Disabled (ENABLE_PROGRESSIVE_SCHEMAS=False) |
| One-way exposure | Yes — once exposed, never removed |

---

## 8. Implemented vs Missing

| Subsystem | Status | Evidence | Notes |
|---|---|---|---|
| **FastMCP server (SSE)** | ✅ Implemented | supervisor.py:562 `mcp.run(transport="sse")` | Runs on 0.0.0.0:8001 |
| **Tri-state governance** | ✅ Implemented | middleware.py:624-854, state.py:21-27 | BYPASS/READ_ONLY/PERMISSION all functional |
| **Redis state management** | ✅ Implemented | state.py, redis_client.py | Mode, elevations, leases all Redis-backed |
| **Progressive discovery** | ✅ Implemented | supervisor.py:107-150, 289-291 | Mount disabled, on-demand exposure |
| **Tool list filtering** | ✅ Implemented | middleware.py:270-305 | Bootstrap + leased tools only |
| **Lease management** | ✅ Implemented | leases/manager.py | Redis+TTL+Lua consume |
| **Capability tokens (HMAC)** | ✅ Implemented | governance/tokens.py | Generate + verify with full validation |
| **Scoped elevation cache** | ✅ Implemented | state.py:190-241 | SHA256 keys + Redis TTL |
| **Policy engine** | ✅ Implemented | governance/policy.py | Deterministic matrix evaluation |
| **Multi-provider approval** | ✅ Implemented | governance/approval.py | DBus, FastMCP Elicit, systemd — with auto-select |
| **Approval artifacts** | ✅ Implemented | governance/artifacts.py | HTML + JSON artifacts with path safety |
| **Session key management** | ✅ Implemented | governance/session_key.py | Generate, write (0o400), rotate after use |
| **Structured audit logging** | ✅ Implemented | audit.py | JSON Lines, rotation, buffered writes |
| **TOON output encoding** | ✅ Implemented | toon/encoder.py | Array compression active |
| **Agent hook system** | ✅ Implemented (opt-in) | hooks/ | Gates + manager + models. Disabled by default (no agents.yaml) |
| **Workspace path containment** | ✅ Implemented | core_tools.py:22-47 | `_validate_path()` prevents traversal |
| **Tool registry (YAML)** | ✅ Implemented | registry/registry.py | Loaded from config/tools.yaml |
| **Keyword search** | ✅ Implemented | registry/registry.py:160-238 | Fallback when semantic disabled |
| **Schema minimization** | ⚠️ Implemented but disabled | schemas/minimizer.py, config.py:181 | `ENABLE_PROGRESSIVE_SCHEMAS=False` |
| **Schema expansion** | ⚠️ Partially implemented | schemas/expander.py | Functions exist but `expand_tool_schema` tool removed |
| **Semantic retrieval** | ⚠️ Implemented but disabled | retrieval/, rag/ | `ENABLE_SEMANTIC_RETRIEVAL=False` |
| **Macros (batch ops)** | ⚠️ Code exists, flag enabled | macros/ | `ENABLE_MACROS=True` but no macro tools registered in supervisor |
| **RAG pipeline** | ⚠️ Code exists, not wired | rag/ (16 files) | Not imported or invoked from supervisor/middleware |
| **Redis session→agent mapping** | 🔲 Stub | agent_detector.py:53-86 | `get_agent_id_for_session()` returns None |
| **Notification callbacks** | 🔲 Stub | leases/manager.py:393-432 | Callback list exists but never populated in runtime |
| **Metrics handler** | 🔲 Stub | redis_client.py:21-42 | Protocol defined, setter exists, never invoked |
| **Validate no auto-mounts** | 🔲 Stub | validation.py:82-99 | Always returns True (placeholder) |
| **Rate limiting** | ❌ Missing | — | No implementation anywhere |
| **Token revocation list** | ❌ Missing | — | No CRL mechanism |
| **HMAC key rotation** | ❌ Missing | — | Static env var only |
| **Distributed mode-change lock** | ❌ Missing | — | No Redis SETNX/Redlock |

---

## 9. Highest-Risk Gaps

### 1. No Rate Limiting on Lease Grants

**Risk:** A client can call `get_tool_schema()` in a tight loop to generate unlimited leases and capability tokens, effectively bypassing the call-limited lease system.

**Evidence:** `supervisor.py:331-504` has no rate check. `lease_manager.grant()` has no per-client rate limit.

### 2. Lease Management Can Be Fully Disabled via Config

**Risk:** Setting `ENABLE_LEASE_MANAGEMENT=False` disables ALL lease checks, token verification, AND tool list filtering. The middleware explicitly skips both lease validation (middleware.py:653) and list filtering (middleware.py:279-281).

**Evidence:** `config.py:180`: `ENABLE_LEASE_MANAGEMENT: bool = True` — env-var overridable.

### 3. HMAC Secret Has Insecure Default

**Risk:** Default HMAC secret is a well-known string: `"default_dev_secret_change_in_production_32bytes_minimum"` (config.py:161). In non-production environments, config validation only warns — it does not block startup.

**Evidence:** `config.py:160-162`. Production enforcement only triggers when `ENVIRONMENT=production` (config.py:207).

### 4. RAG/Semantic/Macros Code Exists but Is Not Wired

**Risk:** 16+ files in `rag/`, `retrieval/`, and `macros/` directories exist with substantial code but are not imported or invoked from the server runtime. This is dead code that increases attack surface and maintenance burden.

**Evidence:** No imports of `rag.*` in supervisor.py or middleware.py. `ENABLE_SEMANTIC_RETRIEVAL=False`, `ENABLE_MACROS=True` but no macro tools registered.

### 5. Notification Callbacks Never Registered

**Risk:** `lease_manager._emit_list_changed()` (leases/manager.py:393-413) is called on every lease grant/revoke/exhaust, but `_notification_callbacks` list is always empty because `register_notification_callback()` is never called in the runtime startup path.

**Evidence:** Grep for `register_notification_callback` finds only the definition and test usage — no invocation in supervisor.py or middleware.py.

### 6. One-Way Tool Exposure

**Risk:** Once `_expose_tool()` adds a tool via `mcp.add_tool()`, there is no mechanism to remove it. Tools exposed during a session remain visible even after their leases expire. The only mitigation is the `on_list_tools()` filter, but tools remain callable if the client knows the name.

**Evidence:** No `mcp.remove_tool()` call exists anywhere. `_loaded_tools` set only grows.

---

## 10. Resume Point for Development

Based on code evidence, development most likely left off at:

### Most Recent Active Work

1. **Phase 8 (Notifications)**: `_emit_list_changed()` is called throughout lease manager but callback registration is not wired — this is the most recently scaffolded feature that lacks completion.

2. **Agent hook system integration**: Fully implemented in `hooks/` but the activation mechanism (creating `config/agents.yaml`) is not part of any automated workflow. The middleware integration is complete but the feature is dormant.

3. **Feature flag cleanup**: Three feature flags exist (`ENABLE_SEMANTIC_RETRIEVAL`, `ENABLE_PROGRESSIVE_SCHEMAS`, `ENABLE_MACROS`). The first two are off; macros is on but tools aren't registered. These represent in-progress feature gates.

### Suggested Next Steps (Based on Code State)

1. Wire `register_notification_callback()` in supervisor lifespan to enable MCP `tools/list_changed` notifications
2. Register macro tools in supervisor if `ENABLE_MACROS` is intended to be active
3. Add rate limiting on `get_tool_schema()` to prevent lease flooding
4. Implement tool de-exposure (remove from `mcp` when lease expires) for true progressive discovery
5. Consider removing or isolating the RAG/semantic modules until they are wired into the server

---

*This audit was generated from forensic source code inspection. All claims are grounded in specific file paths and function references. No documentation or README claims were used as evidence.*
