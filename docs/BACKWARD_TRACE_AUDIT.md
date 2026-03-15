# Backward-Trace Forensic Code Audit

**Repository:** itstanner5216/MetaServer  
**Audit type:** Backward-trace, code-only, runtime-first  
**Evidence basis:** Executable source code, runtime wiring, config affecting runtime behavior

---

## 1. Reality-from-the-outside Summary

MetaServer is a FastMCP-based MCP (Model Context Protocol) server that exposes tools to LLM agents through HTTP/SSE transport. At runtime, it surfaces exactly **two bootstrap tools** at all times (`search_tools`, `get_tool_schema`), plus any tools that have been explicitly unlocked by the progressive discovery flow. All tool invocations pass through a single `GovernanceMiddleware` class that enforces a Redis-backed tri-state execution mode (`READ_ONLY`, `PERMISSION`, `BYPASS`). A lease-and-capability-token system controls which tools a given session may call, and an optional agent hook system (off by default) layers additional per-agent policy gates on top.

The core governance, lease, token, and audit subsystems are **all live and wired**. Several optional features (semantic search, TOON encoding, agent hooks, progressive schemas) are feature-flagged off by default or conditioned on external config files that may not exist.

---

## 2. Runtime Surfaces Inventory

| Surface | File path | Symbol | Why runtime-reachable | Immediate responsibility |
|---|---|---|---|---|
| MCP server entrypoint | `src/meta_mcp/__main__.py` | `main()` via import | Invoked by `python -m meta_mcp` | Delegates to `supervisor.main()` |
| HTTP/SSE server startup | `src/meta_mcp/supervisor.py:562` | `mcp.run(transport="sse", ...)` | Called from `main()` | Starts FastMCP server on `HOST:PORT` |
| Bootstrap tool: search | `src/meta_mcp/supervisor.py:299` | `search_tools` | `@mcp.tool()` decorator at module load | Keyword/semantic search over tool registry |
| Bootstrap tool: schema | `src/meta_mcp/supervisor.py:330` | `get_tool_schema` | `@mcp.tool()` decorator at module load | Progressive discovery trigger; exposes tools |
| Tool list filter | `src/meta_mcp/middleware.py:270` | `GovernanceMiddleware.on_list_tools` | Called by FastMCP for every `tools/list` request | Hides non-leased tools from clients |
| Tool execution gate | `src/meta_mcp/middleware.py:624` | `GovernanceMiddleware.on_call_tool` | Called by FastMCP for every tool invocation | Lease check → token check → hook → mode enforcement → approval elicitation |
| Server lifecycle | `src/meta_mcp/supervisor.py:159` | `lifespan()` | Registered as `FastMCP(..., lifespan=lifespan)` | Redis check, session key init, registry load, compliance validation, approval provider init |
| Dynamically exposed tools | `src/meta_mcp/supervisor.py:107` | `_expose_tool()` | Called inside `get_tool_schema()` | Adds individual tools to MCP via `mcp.add_tool()` |

---

## 3. Backward Traces

### 3.1 Tool Execution Flow

**Behavior / exposed effect:** Client calls a tool (e.g., `write_file`)  
**Surface entrypoint:** `GovernanceMiddleware.on_call_tool` (`middleware.py:624`)  
**Immediate handler:** FastMCP routes the call through the `middleware` list registered at `supervisor.py:271`: `mcp = FastMCP(name=SERVER_NAME, middleware=[GovernanceMiddleware()], lifespan=lifespan)`  

**Upstream dependency chain:**
1. `on_call_tool` extracts `tool_name`, `arguments`, `session_id` from `context.request_context`
2. If `ENABLE_LEASE_MANAGEMENT=True` (default) and tool is not a bootstrap tool:
   - `lease_manager.validate(client_id, tool_name)` → Redis GET `lease:{client_id}:{tool_name}`
   - If lease has `capability_token`: `verify_token(...)` → HMAC-SHA256 check with `Config.HMAC_SECRET`
3. `detect_agent_id(context)` → checks `ctx.metadata`, `ctx.request_context.agent_id`, or `MCP_AGENT_ID` env var
4. If `hook_manager.is_agent_mode(agent_id)`: runs `run_before_tool_call(session_id, tool_name, arguments)`
5. Audit: `audit_logger.log_tool_call(...)` → writes JSON line to `audit.jsonl`
6. `governance_state.get_mode()` → Redis GET `governance:mode`; fail-safe to `PERMISSION`
7. Mode dispatch:
   - `BYPASS` → execute immediately, audit `BYPASS_EXECUTED`
   - non-sensitive tool (not in `SENSITIVE_TOOLS` set) → execute immediately
   - `READ_ONLY` + sensitive → raise `ToolError`, audit `BLOCKED_READ_ONLY`
   - `PERMISSION` + sensitive → check elevation → elicit approval → execute or deny

**Origin of data / permission / tool / schema / context:**
- `SENSITIVE_TOOLS` constant hardcoded in `middleware.py:33-43`
- Governance mode from Redis key `governance:mode`, initialized from `Config.DEFAULT_EXECUTION_MODE` (env var `DEFAULT_GOVERNANCE_MODE`, default `"permission"`)
- Lease from Redis, granted by `get_tool_schema()` at schema request time
- Capability token: HMAC-SHA256 signed with `Config.HMAC_SECRET`

**Actual enforcement points:**
- Lease check: `middleware.py:662` — blocks with `ToolError` if no valid lease
- Token check: `middleware.py:672-692` — verifies HMAC signature, expiration, client_id, tool_id binding
- Hook gate: `middleware.py:704-722` — blocks with `ToolError` on `PolicyViolation`
- Mode enforcement: `middleware.py:760-854` — all three mode paths enforced

**Failure behavior:**
- No lease → `ToolError("No valid lease for tool...")`
- Invalid token → lease revoked, `ToolError("Invalid capability token...")`
- READ_ONLY + sensitive → `ToolError("...blocked: System is in READ_ONLY mode")`
- PERMISSION + denied → `ToolError("...denied: User did not approve")`
- Unknown mode → `ToolError("...denied: Unknown governance mode")`
- Redis failure during `get_mode()` → fail-safe: mode = `PERMISSION`

**Evidence:** `middleware.py:624-854`, `state.py:92-138`, `leases/manager.py:90-150`

---

### 3.2 Permission Behavior

**Behavior:** PERMISSION mode blocks sensitive tool calls until user approves  
**Surface entrypoint:** `GovernanceMiddleware.on_call_tool` mode dispatch at `middleware.py:794`

**Upstream dependency chain:**
1. `_check_elevation(tool_name, arguments, session_id)` → `governance_state.check_elevation(hash_key)` → Redis EXISTS `elevation:{sha256(tool+context+session)}`
2. If elevation exists: allow without further prompting
3. If no elevation: `_elicit_approval(ctx, tool_name, arguments)`:
   a. Computes `request_id`, `context_key`, `required_scopes`
   b. Generates HTML and JSON artifacts via `ApprovalArtifactGenerator`
   c. Gets approval provider via `get_approval_provider(context=ctx)`
   d. `provider.request_approval(approval_request)` — blocks awaiting response
   e. Validates response: checks `selected_scopes` covers all `required_scopes`
   f. If approved with `lease_seconds > 0`: grants elevation in Redis with TTL
4. Result returned to `on_call_tool`

**Origin of data:**
- `required_scopes` from `tool_registry.get(tool_name).required_scopes` (from `config/tools.yaml`) + resource-specific scopes appended from arguments
- Elevation key: `SHA256(tool_name:context_key:session_id)`, stored in Redis under `elevation:` prefix
- Approval response: from `DBusGUIProvider`, `FastMCPElicitProvider`, or `SystemdAskPasswordProvider`

**Actual enforcement:** Scope validation at `middleware.py:543-574` — empty scopes, missing scopes, and extra scopes all result in denial

**Failure behavior:** Any exception in `_elicit_approval` → `return False, 0, []` (fail-safe denial, `middleware.py:609-622`)

**Evidence:** `middleware.py:371-622`, `state.py:190-226`, `governance/approval.py:78-400+`

---

### 3.3 Progressive Discovery

**Behavior:** Only bootstrap tools are visible in `tools/list` at startup  
**Surface entrypoint:** `GovernanceMiddleware.on_list_tools` (`middleware.py:270`)

**Upstream dependency chain:**
1. If `not Config.ENABLE_LEASE_MANAGEMENT`: return full list (bypass filtering)
2. `bootstrap_tools = set(tool_registry.get_bootstrap_tools()) | {"expand_tool_schema"}` — always `{"search_tools", "get_tool_schema", "expand_tool_schema"}`. Note: `expand_tool_schema` is a stale reference — the tool was deprecated and removed from the server (`supervisor.py:507-510`) but still appears here. It is never registered and cannot be called.
3. For each non-bootstrap tool: `lease_manager.validate(client_id, tool_name)` → only include if valid lease exists
4. Client calls `get_tool_schema(tool_name)`:
   - Policy evaluated: `evaluate_policy(mode, risk_level, tool_id)`
   - If `allow`: `_expose_tool(tool_name)` → `mcp.add_tool(tool_instance)` + `_loaded_tools.add(tool_name)`
   - Lease granted: `lease_manager.grant(client_id, tool_id, ttl, calls, mode, token)`
   - Tool now appears in `tools/list` for that session

**Origin of tools registry:** `ToolRegistry.from_yaml(config/tools.yaml)` at module import time (`registry.py:265-268`)

**Actual enforcement:** `on_list_tools` checks live lease for every non-bootstrap tool every time `tools/list` is called. Lease expiry in Redis naturally removes the tool from the visible list.

**Evidence:** `middleware.py:270-305`, `supervisor.py:330-504`, `registry/registry.py:265-268`

---

### 3.4 Schema Minimization

**Behavior:** `get_tool_schema()` returns a stripped schema (no descriptions, examples, defaults)  
**Surface entrypoint:** `get_tool_schema` tool handler at `supervisor.py:330`

**Upstream dependency chain:**
1. If `expand=True`: return `tool_record.schema_full` or raw `mcp_tool.inputSchema`
2. If `expand=False` AND `Config.ENABLE_PROGRESSIVE_SCHEMAS=True`:
   - `minimize_schema(input_schema)` is called from `schemas/__init__.py`
   - Stores `schema_full` and `schema_min` on `tool_record`
   - Returns `schema_min` to client
3. If `ENABLE_PROGRESSIVE_SCHEMAS=False` (default): returns raw `mcp_tool.inputSchema` without minimization

**Origin:** `schemas/minimizer.py:minimize_schema()` — strips `description`, `examples`, `default`, `title` from all properties

**Actual enforcement:** Only active when `Config.ENABLE_PROGRESSIVE_SCHEMAS=True` (default: `False` per `config.py:181`)

**Evidence:** `supervisor.py:471-491`, `config.py:181`, `schemas/minimizer.py:22-96`

---

## 4. Permission System Backward Audit

### Enforcement nearest execution

The final enforcement point is `GovernanceMiddleware.on_call_tool` (`middleware.py:624`). Execution only proceeds past this gate if ALL of the following are satisfied:

1. **Lease valid** (if `ENABLE_LEASE_MANAGEMENT=True`): `lease_manager.validate()` returns a non-None `ToolLease` from Redis
2. **Capability token valid** (if lease has `capability_token`): `verify_token()` passes HMAC-SHA256, expiry, and binding checks
3. **Agent hook passes** (if agent binding configured): all `Gate.check()` calls return no `PolicyViolation`
4. **Governance mode allows**:
   - `BYPASS`: always allows
   - Not a sensitive tool: always allows
   - `READ_ONLY` + sensitive: always blocks
   - `PERMISSION` + sensitive: requires elevation or fresh approval

### What data enforcement relies on

| Check | Data source | Established where |
|---|---|---|
| Governance mode | Redis key `governance:mode` | `lifespan()` sets default; `set_mode()` changes it |
| Lease existence | Redis key `lease:{client_id}:{tool_id}` | `lease_manager.grant()` in `get_tool_schema()` |
| Token validity | Encoded in lease JSON, verified with `HMAC_SECRET` | `generate_token()` + `verify_token()` in `governance/tokens.py` |
| Elevation existence | Redis key `elevation:{sha256}` | `_grant_elevation()` after user approves |
| Agent binding | In-memory `_bindings` dict in `HookManager` | Loaded from `config/agents.yaml` at startup |

### Where legitimacy is established

- **Governance mode legitimacy**: Requires valid session key (`GovernanceKeyManager.validate_and_rotate()`) to change. Key is a random secret written to `Config.GOVERNANCE_KEY_DIR` at startup and consumed on use (rotated).
- **Lease legitimacy**: Granted only after `evaluate_policy()` returns `allow` in `get_tool_schema()`. Policy is deterministic based on mode + risk level.
- **Token legitimacy**: HMAC-SHA256 signed at grant time with `Config.HMAC_SECRET`. Token binding includes `client_id` and `tool_id`.

### Where legitimacy is only assumed

- **Client identity** (`client_id`): Derived from `ctx.session_id` in FastMCP context. If the MCP transport layer allows session hijacking, the lease isolation per `client_id` could be bypassed. This is assumed trusted at the transport layer.
- **Approval scope matching**: Required scopes come from `tool_record.required_scopes` in `tools.yaml`. The file is loaded statically at startup — if `tools.yaml` is tampered with, required scopes could be weakened.
- **Agent ID detection**: `detect_agent_id()` checks `ctx.metadata`, environment variable `MCP_AGENT_ID`, and `ctx.request_context.agent_id`. An attacker who controls the MCP request metadata could spoof an agent_id to trigger (or avoid) hook enforcement.

### What breaks if upstream assumptions fail

- Redis unavailable → `get_mode()` returns `PERMISSION` (fail-safe). Lease operations return `None` → tool calls blocked. Session key operations fail → mode changes disabled.
- `HMAC_SECRET` is default value (`"default_dev_secret_change_in_production_32bytes_minimum"`) → tokens can be forged by anyone who knows the default.
- `tools.yaml` missing or malformed → `ToolRegistry.from_yaml()` raises `FileNotFoundError` or `ValueError` at import time, preventing server startup entirely.

---

## 5. Hooks Backward Audit

### Where hooks visibly affect runtime behavior

1. **before_tool_call** (`middleware.py:705-722`): If a gate returns a `PolicyViolation`, the tool call is blocked with `ToolError` and audited as `BLOCKED_READ_ONLY` with reason `agent_hook:{gate_type}`.
2. **after_tool_result** (`middleware.py:724-729`, `771`, `779`, `812`, `840`): Executed after every successful or failed tool call when in agent mode. Finalizes receipt; runs custom post-execution hooks.

### Where those hook calls originate

- `middleware.py:701-706`: `agent_id = detect_agent_id(context)` → `if hook_manager.is_agent_mode(agent_id):`
- `hook_manager.is_agent_mode()` returns `True` only if `_enabled=True` AND `agent_id in _bindings`
- `_enabled` is set to `True` only when `config/agents.yaml` exists, has `enabled: true`, and contains at least one agent binding (`hooks/manager.py:71-137`)

### What data hooks receive

Gates receive the `AgentRunContext` (which holds `AgentBinding` with `allowed_tools`, `denied_tools`, `allowed_paths`, `denied_paths`, `max_tool_calls`), `tool_name`, and `arguments`.

### Whether hooks are mandatory, optional, bypassable, or partially wired

- **Optional**: Hooks are entirely disabled if `config/agents.yaml` does not exist or is empty. The default repo has no `config/agents.yaml` file, so hooks are off by default.
- **Bypassable**: If `detect_agent_id(context)` returns `None` (no agent ID in metadata, request context, or `MCP_AGENT_ID` env var), hooks do not run regardless of `config/agents.yaml` contents.
- **Partially wired**: `get_agent_id_for_session()` and `set_agent_id_for_session()` in `agent_detector.py` are documented as stubs that always return `None`/`False`. Session→agent ID persistence via Redis is explicitly planned but not implemented.

**Evidence:** `hooks/manager.py:54-170`, `middleware.py:699-729`, `agent_detector.py:53-87`

---

## 6. Context Minimization Backward Audit

### Where minimized context appears in a live path

Two distinct minimization mechanisms exist:

**Tool list minimization (live):** `GovernanceMiddleware.on_list_tools` (`middleware.py:270`) hides all non-bootstrap tools unless a lease exists for the session. This is active whenever `Config.ENABLE_LEASE_MANAGEMENT=True` (default).

**Schema minimization (feature-flagged off):** `get_tool_schema(tool_name, expand=False)` with `Config.ENABLE_PROGRESSIVE_SCHEMAS=True` returns stripped schemas. Default configuration has `ENABLE_PROGRESSIVE_SCHEMAS=False` (`config.py:181`), so full schemas are returned.

### What code created it

- Tool list minimization: implemented in `on_list_tools` using `lease_manager.validate()` per tool
- Schema minimization: `minimize_schema(input_schema)` from `schemas/minimizer.py:22-96`

### What upstream selection/filtering logic produced it

- Tool list: only tools with valid leases (Redis) + bootstrap tools are returned
- Schema: strips `description`, `examples`, `default`, `title` from all property schemas recursively; preserves `type`, `enum`, `items`, `properties`, `required`

### Whether it is guaranteed, optional, or not truly enforced

- **Tool list minimization**: Enforced at runtime when `ENABLE_LEASE_MANAGEMENT=True`. Setting this to `False` causes `on_list_tools` to return all tools (`middleware.py:279-281`).
- **Schema minimization**: Optional and off by default (`ENABLE_PROGRESSIVE_SCHEMAS=False`). When off, clients receive full schemas including descriptions.

---

## 7. Tools and Schemas Backward Audit

### What is exposed externally

At startup: exactly 2 tools (`search_tools`, `get_tool_schema`). Additional tools become visible per-session only after `get_tool_schema(tool_name)` is called for them and a lease is granted.

### What registry/source generated that exposure

- **Tool registry**: Loaded from `config/tools.yaml` at module import via `ToolRegistry.from_yaml()` (`registry.py:265-268`). The `config/tools.yaml` file defines tools across three categories: 2 bootstrap (`search_tools`, `get_tool_schema`), core tools (file/git operations), and admin tools (`get_governance_status`). The `_get_tool_function()` function in `supervisor.py:72-87` explicitly enumerates 9 core tools and 1 admin tool, confirming at least 12 non-bootstrap tools are handled by the dynamic exposure path.
- **Bootstrap tools**: Decorated with `@mcp.tool()` directly on the `mcp` FastMCP instance (`supervisor.py:299`, `supervisor.py:330`). They are permanently registered.
- **Core/admin tools**: Registered in separate `core_server` and `admin_server` FastMCP instances (`servers/core_tools.py`, `servers/admin_tools.py`). Retrieved via `core_server.get_tool(tool_name)` or `admin_server.get_tool(tool_name)`, then added to `mcp` via `mcp.add_tool(tool_instance)`.

### What filters/gates are applied

1. **Registry check**: `tool_registry.is_registered(tool_name)` in `get_tool_schema()` — blocks unknown tools
2. **Policy evaluation**: `evaluate_policy(mode, risk_level, tool_id)` — blocks or requires approval based on mode/risk matrix
3. **Lease check**: `on_list_tools` hides tools with no active lease
4. **Token check**: `verify_token()` in `on_call_tool` — validates HMAC binding

### Whether exposure is static, dynamic, permission-gated, partially gated, or cosmetic

- **Bootstrap tools**: Static, always exposed, not permission-gated (policy explicitly bypasses them at `governance/policy.py:57-62`)
- **Core/admin tools**: Dynamic (on-demand via `_expose_tool()`), permission-gated (policy evaluated before exposure), lease-gated (lease required to call after exposure), and token-gated (HMAC token verified on call)
- **Schema exposure**: Dynamic (full or minimal based on `expand` parameter and `ENABLE_PROGRESSIVE_SCHEMAS` flag). If progressive schemas are off, full schema is always returned on any tool the policy allows.

---

## 8. Live vs Dead vs Partial

| Subsystem | Status | Runtime evidence | Backward-trace notes |
|---|---|---|---|
| FastMCP server startup | **Live** | `supervisor.py:562` `mcp.run(transport="sse")` | Always executes in `main()` |
| Bootstrap tools (search + schema) | **Live** | `@mcp.tool()` at `supervisor.py:299, 330` | Always registered at module load |
| GovernanceMiddleware.on_call_tool | **Live** | Registered as sole middleware at `supervisor.py:271` | All tool calls pass through |
| GovernanceMiddleware.on_list_tools | **Live** | FastMCP hook, called on every tools/list | Active when `ENABLE_LEASE_MANAGEMENT=True` |
| Redis-backed governance mode | **Live** | `state.py:92-138`, Redis key `governance:mode` | Fail-safe to PERMISSION on error |
| Lease management | **Live** | `leases/manager.py`, Redis key `lease:{client}:{tool}` | Default-enabled, Lua atomics |
| HMAC capability tokens | **Live** | `governance/tokens.py`, verified in `middleware.py:674-692` | Active when lease has token |
| Scoped elevation | **Live** | `state.py:197-226`, Redis key `elevation:{hash}` | SHA256-keyed, TTL-enforced |
| Approval elicitation | **Live (conditional)** | `middleware.py:371-622`, calls `get_approval_provider()` | Requires PERMISSION mode + sensitive tool |
| DBus GUI approval provider | **Partial** | `governance/approval.py:118-227` | Requires `dasbus` lib + GNOME Shell extension |
| FastMCP Elicit approval provider | **Partial** | `governance/approval.py:230-356` | Requires FastMCP client supporting `ctx.elicit()` |
| Systemd password provider | **Partial** | `governance/approval.py` (not fully traced) | Terminal fallback, platform-specific |
| Approval artifacts (HTML/JSON) | **Live** | `middleware.py:403-441`, `governance/artifacts.py` | Generated before every elicitation |
| Audit logging | **Live** | `audit.py:436-438` module-level singleton, called throughout `middleware.py` | JSON Lines, rotating file |
| Agent hooks (HookManager) | **Partial** | `hooks/manager.py:54-413`, called in `middleware.py:701-729` | Disabled unless `config/agents.yaml` exists |
| Tool allowlist gate | **Live (conditional)** | `hooks/gates.py:39-72` | Only active when hooks enabled |
| Path fence gate | **Live (conditional)** | `hooks/gates.py:75-200` | Only active when hooks enabled |
| Budget gate (max_tool_calls) | **Live (conditional)** | `hooks/manager.py:303` `ctx.increment_tool_call()` | Only active when hooks enabled |
| Agent session Redis persistence | **Stub** | `agent_detector.py:53-87` — returns `None`/`False` always | Planned but not implemented |
| Schema minimization | **Partial** | `schemas/minimizer.py:22-96` | Only active when `ENABLE_PROGRESSIVE_SCHEMAS=True` (default False) |
| Semantic search | **Partial** | `registry/registry.py:181-196` | Only active when `ENABLE_SEMANTIC_RETRIEVAL=True` (default False) |
| RAG pipeline | **Partial** | `rag/` directory, `retrieval/` directory | Code present, requires Qdrant + embeddings configured |
| TOON encoding | **Partial** | `middleware.py:66-84`, `toon/encoder.py` | `Config.ENABLE_TOON_OUTPUTS=True` by default, active on all results |
| Macro tools (batch ops) | **Partial** | `macros/` directory | `ENABLE_MACROS=True` default, but not wired as MCP tools in supervisor |
| Dynamic tool discovery (legacy) | **Dead** | `mcp.mount()` calls at `supervisor.py:290-291` are commented out | Replaced by progressive discovery |
| `expand_tool_schema` tool | **Dead** | Referenced in `on_list_tools` bootstrap set but never registered | Comment at `supervisor.py:507-510` says deprecated |
| Session→agent ID Redis mapping | **Stub** | `agent_detector.py:53-87` | Declared, never wired to Redis |

---

## 9. Highest-Risk False Assumptions

1. **Default HMAC secret in production** (`config.py:160-162`): `Config.HMAC_SECRET` defaults to `"default_dev_secret_change_in_production_32bytes_minimum"`. If this is not overridden via `HMAC_SECRET` env var, all capability tokens can be forged by any client that knows the default. The secret is validated in `Config.validate()` only as a warning, not a fatal error except in `ENVIRONMENT=production`.

2. **Client identity from session_id** (`middleware.py:659`): The lease isolation relies entirely on `ctx.session_id` being unforgeable. The transport layer (HTTP/SSE) is trusted to enforce session identity. There is no in-middleware validation that a session has not been hijacked.

3. **Agent ID spoofing** (`middleware.py:702`, `agent_detector.py:27-44`): `detect_agent_id()` reads from `ctx.metadata.get("agent_id")` first. MCP clients that send metadata can set arbitrary agent IDs. If an attacker sends a matching `agent_id` for a configured binding, hook enforcement is triggered for that agent's policy. Conversely, a client could avoid hook enforcement by not sending any `agent_id`. The hook system is opt-in and is not a security boundary.

4. **Policy evaluation in `get_tool_schema()` is not the final gate** (`supervisor.py:373-399`): Policy is checked when a client requests a schema. However, the enforcement at execution time (`on_call_tool`) does NOT re-evaluate policy; it only checks lease existence. If the governance mode changes between `get_tool_schema()` and the actual tool call, the lease remains valid and the call proceeds under the old mode's permission. A lease granted under `BYPASS` mode survives a switch back to `PERMISSION` mode until it expires.

5. **`tools.yaml` as a trusted source** (`registry.py:265-268`): The tool registry including `required_scopes` is loaded statically at startup from `config/tools.yaml`. There is no integrity check on this file. If it is modified after deployment, a server restart would load potentially weakened scope requirements.

6. **`expand_tool_schema` in bootstrap set** (`middleware.py:283`): `on_list_tools` always includes `"expand_tool_schema"` in the bootstrap tools set, even though this tool was deprecated and removed (`supervisor.py:507-510`). The tool is never registered in the MCP server. This creates an inconsistency: the tool filter claims it should always be visible, but it doesn't exist and cannot be called.

7. **Approval provider selection is runtime-conditional** (`governance/approval.py:get_approval_provider()`): The approval provider is selected at runtime based on environment availability (DBus, FastMCP elicit). If no provider is available and a PERMISSION-mode approval is required, the approval flow returns an ERROR decision, which is handled as a denial. This is fail-safe but could prevent all sensitive operations if the deployment environment has no working approval provider.

---

## 10. Likely Project Resume Point

Based on code-backed backward tracing, development most recently focused on **Phase 4 (capability tokens)** and the **approval elicitation wiring**, with the following evidence:

- Capability token generation (`governance/tokens.py`) and verification (`middleware.py:674-692`) are fully wired and tested.
- The approval artifact system (`governance/artifacts.py`) is wired into `_elicit_approval()` in the middleware with non-fatal artifact generation errors.
- Feature flags `ENABLE_PROGRESSIVE_SCHEMAS=False` and `ENABLE_SEMANTIC_RETRIEVAL=False` are explicitly set as defaults, indicating Phase 5 (progressive schemas) and Phase 2 (semantic retrieval) are not yet production-ready.
- `ENABLE_MACROS=True` but macro tools are not wired as MCP tools in `supervisor.py` — the macro code exists in `macros/` but is not registered with the server.
- Agent session persistence via Redis (`agent_detector.py:53-87`) is explicitly documented as a stub ("Stub: returns None").
- The `expand_tool_schema` deprecated tool is still referenced in `on_list_tools`' bootstrap set but was removed from the server, indicating a cleanup task was started but not completed.

The most likely next development steps are:
1. Wire macro tools into the supervisor as MCP tools (batch operations)
2. Enable and harden `ENABLE_PROGRESSIVE_SCHEMAS`
3. Implement Redis-backed session→agent ID persistence in `agent_detector.py`
4. Remove the stale `expand_tool_schema` reference from `on_list_tools`

---

## Evidence Index

| Conclusion | File | Symbol/Lines |
|---|---|---|
| Only 2 bootstrap tools at startup | `supervisor.py:299, 330` | `search_tools`, `get_tool_schema` decorated with `@mcp.tool()` |
| Single middleware handles all calls | `supervisor.py:271` | `mcp = FastMCP(..., middleware=[GovernanceMiddleware()])` |
| Lease check is first gate on call | `middleware.py:653-670` | `lease_manager.validate(client_id, tool_name)` |
| HMAC token verification | `middleware.py:673-692` | `verify_token(token, client_id, tool_id, secret)` |
| Hooks only run if agent binding exists | `hooks/manager.py:155-169` | `is_agent_mode()` returns False when `_enabled=False` |
| Hooks disabled without agents.yaml | `hooks/manager.py:82-87` | `if not config_path.exists(): return False` |
| Policy matrix is deterministic | `governance/policy.py:24-116` | `evaluate_policy(mode, tool_risk, tool_id)` |
| Governance mode fail-safe | `state.py:125-138` | Redis error → `return ExecutionMode.PERMISSION` |
| Schema minimization is off by default | `config.py:181` | `ENABLE_PROGRESSIVE_SCHEMAS: bool = False` |
| Tool list hides non-leased tools | `middleware.py:270-305` | `on_list_tools` checks lease per tool |
| Progressive discovery trigger | `supervisor.py:415-420` | `_expose_tool(tool_name)` called inside `get_tool_schema()` |
| Capability token default secret risk | `config.py:160-162` | `HMAC_SECRET` defaults to hardcoded string |
| Agent session persistence is stub | `agent_detector.py:53-87` | `get_agent_id_for_session` returns `None` always |
| expand_tool_schema is dead code | `supervisor.py:507-510`, `middleware.py:283` | Tool removed but referenced in bootstrap set |
| Audit logging is always-on | `audit.py:436-438` | Module-level singleton `audit_logger = AuditLogger()` |
| Approval denial fail-safe | `middleware.py:609-622` | Exception in elicitation → `return False, 0, []` |
