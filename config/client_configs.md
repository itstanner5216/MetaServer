# MCP Client Configuration Guide

This guide covers how to connect desktop clients to the Meta-Supervisor MCP server using stdio transport via the supergateway bridge.

---

## Architecture Overview

```
┌──────────────────┐
│  Desktop Client  │
│ (Claude/Cursor/  │
│    VS Code)      │
└────────┬─────────┘
         │ stdio (JSON-RPC)
         ▼
┌──────────────────┐
│  supergateway    │
│  (npx package)   │
└────────┬─────────┘
         │ HTTP/SSE
         ▼
┌──────────────────┐
│ meta-supervisor  │
│   (port 8001)    │
└────────┬─────────┘
         │ MCP Protocol
         ▼
┌──────────────────┐
│   Tools +        │
│   Governance     │
└──────────────────┘
```

**Why supergateway?**
- Desktop clients expect stdio transport (stdin/stdout)
- Meta-supervisor uses HTTP/SSE transport (Docker compatible)
- supergateway bridges stdio ↔ HTTP/SSE protocols

---

## Prerequisites

### 1. Install Node.js

supergateway requires Node.js (v16+):

**Windows:**
```powershell
# Download from https://nodejs.org/
# Or use Chocolatey:
choco install nodejs
```

**macOS:**
```bash
brew install node
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt install nodejs npm

# Fedora
sudo dnf install nodejs
```

Verify installation:
```bash
node --version  # Should be v16+
npm --version
```

### 2. Ensure Meta-Supervisor is Running

Before configuring clients, start meta-supervisor:

```bash
cd C:\Projects\MCPServer
uv run python -m meta_mcp.supervisor
```

Verify it's running:
```bash
curl http://localhost:8001/health
```

---

## Client Configurations

### 1. Claude Desktop

**Configuration File Location:**

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

**Configuration:**

```json
{
  "mcpServers": {
    "MetaSupervisor": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--streamableHttp",
        "http://localhost:8001/mcp"
      ]
    }
  }
}
```

**Explanation:**
- `npx -y`: Automatically install and run supergateway
- `--streamableHttp`: Convert HTTP/SSE to stdio
- `http://localhost:8001/mcp`: Meta-supervisor MCP endpoint

**Steps:**

1. **Open configuration file:**
   ```powershell
   # Windows PowerShell
   notepad $env:APPDATA\Claude\claude_desktop_config.json
   ```

   ```bash
   # macOS/Linux
   code ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. **Add the configuration above**

3. **Restart Claude Desktop**

4. **Verify connection:**
   - Open Claude Desktop
   - Look for "MetaSupervisor" in MCP servers list
   - Try using a tool: "List files in current directory"

---

### 2. Cursor

**Configuration File Location:**

- **All Platforms:** `~/.cursor/mcp.json`

**Configuration:**

```json
{
  "mcpServers": {
    "MetaSupervisor": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--streamableHttp",
        "http://localhost:8001/mcp"
      ]
    }
  }
}
```

**Steps:**

1. **Create/edit configuration file:**
   ```bash
   # Windows (PowerShell)
   mkdir -Force ~/.cursor
   notepad ~/.cursor/mcp.json

   # macOS/Linux
   mkdir -p ~/.cursor
   code ~/.cursor/mcp.json
   ```

2. **Add the configuration above**

3. **Restart Cursor**

4. **Verify connection:**
   - Open Cursor
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
   - Type "MCP: List Servers"
   - Verify "MetaSupervisor" appears

---

### 3. VS Code (with MCP Extension)

**Prerequisites:**
- Install MCP extension from VS Code marketplace

**Configuration File Location:**

- **Project-specific:** `.vscode/settings.json` (in your workspace)
- **Global:** User settings (File → Preferences → Settings → JSON)

**Configuration:**

```json
{
  "mcp.servers": {
    "MetaSupervisor": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--streamableHttp",
        "http://localhost:8001/mcp"
      ]
    }
  }
}
```

**Steps:**

1. **Open workspace settings:**
   ```
   File → Preferences → Settings
   Click "Open Settings (JSON)" in top-right
   ```

2. **Add the configuration above**

3. **Reload VS Code:**
   ```
   Ctrl+Shift+P → Developer: Reload Window
   ```

4. **Verify connection:**
   - Open Command Palette (`Ctrl+Shift+P`)
   - Type "MCP: Show Servers"
   - Verify "MetaSupervisor" is connected

---

## supergateway Installation

### Auto-Installation (Recommended)

When you use `npx -y supergateway`, npm automatically:
1. Downloads supergateway package
2. Installs it to npm cache
3. Runs the command

**Pros:**
- Always uses latest version
- No manual updates needed
- Works across all clients

### Manual Installation (Optional)

If you prefer to install globally:

```bash
npm install -g supergateway
```

Then update client configs to use global command:

```json
{
  "mcpServers": {
    "MetaSupervisor": {
      "command": "supergateway",  // No npx
      "args": [
        "--streamableHttp",
        "http://localhost:8001/mcp"
      ]
    }
  }
}
```

---

## Network Path Diagram

### Full Request Flow

```
1. User types in Claude Desktop:
   "Read the file config.yaml"

2. Claude Desktop → supergateway (stdio)
   {
     "jsonrpc": "2.0",
     "method": "tools/call",
     "params": {
       "name": "read_file",
       "arguments": {"path": "config.yaml"}
     }
   }

3. supergateway → meta-supervisor (HTTP)
   POST http://localhost:8001/mcp/tools/call
   Content-Type: application/json
   {
     "name": "read_file",
     "arguments": {"path": "config.yaml"}
   }

4. meta-supervisor processes request:
   a. GovernanceMiddleware intercepts
   b. Checks governance mode
   c. Validates path (workspace root)
   d. Executes read_file from core_server
   e. Audits operation

5. Response flows back:
   meta-supervisor → supergateway → Claude Desktop
   {
     "result": "file contents here..."
   }
```

### Governance in Action

```
┌──────────────────────────────────────────────────────┐
│ Tool Call: write_file                                 │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ GovernanceMiddleware.on_call_tool()                   │
│                                                       │
│ Mode: PERMISSION                                      │
│ Tool: write_file (SENSITIVE)                          │
│                                                       │
│ 1. Check scoped elevation → NOT FOUND                 │
│ 2. Elicit approval from user                          │
│    ├─ Format approval request                         │
│    ├─ Wait for user response (max 300s)               │
│    └─ Parse response                                  │
│                                                       │
│ User approves? YES                                    │
│ 3. Grant elevation (TTL=300s)                         │
│ 4. Execute tool                                       │
│ 5. Audit: APPROVAL_GRANTED, ELEVATION_GRANTED         │
└──────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Problem: "Command not found: npx"

**Cause:** Node.js not installed or not in PATH

**Solution:**
```bash
# Verify Node.js installation
node --version
npm --version

# If missing, install Node.js from https://nodejs.org/
```

---

### Problem: "Connection refused to localhost:8001"

**Cause:** Meta-supervisor not running

**Solution:**
```bash
# Start meta-supervisor
cd C:\Projects\MCPServer
uv run python -m meta_mcp.supervisor

# Verify it's running
curl http://localhost:8001/health
```

---

### Problem: "supergateway fails to connect"

**Cause:** Incorrect URL or port

**Solution:**
1. Check meta-supervisor is on port 8001:
   ```bash
   netstat -an | grep 8001
   ```

2. Verify MCP endpoint exists:
   ```bash
   curl http://localhost:8001/mcp
   ```

3. Check firewall isn't blocking localhost

---

### Problem: "Tools not appearing in client"

**Cause:** MCP server not registered correctly

**Solution:**
1. Check client logs for errors
2. Verify configuration file syntax (valid JSON)
3. Restart client completely
4. Check meta-supervisor logs:
   ```bash
   tail -f supervisor.log
   ```

---

### Problem: "Tool execution fails with ToolError"

**Cause:** Governance blocking operation or path validation failing

**Solution:**
1. Check governance mode:
   ```bash
   # In client, call:
   get_governance_status
   ```

2. Check audit log:
   ```bash
   tail -f audit.jsonl | jq
   ```

3. Verify workspace path:
   ```bash
   # Ensure path is within WORKSPACE_ROOT
   # Default: ./workspace
   ```

---

### Problem: "Approval requests timing out"

**Cause:** ELICITATION_TIMEOUT (300s) exceeded

**Solution:**
1. Respond to approval prompts faster
2. If legitimately slow, increase timeout in middleware.py:
   ```python
   ELICITATION_TIMEOUT = 600  # 10 minutes
   ```

3. Check if client properly displays approval requests

---

### Problem: "Redis connection errors"

**Cause:** Redis not running or not reachable

**Solution:**
1. Start Redis:
   ```bash
   # WSL/Linux
   redis-server

   # Docker
   docker run -d -p 6379:6379 redis:latest
   ```

2. Verify Redis is running:
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

3. System will degrade to PERMISSION mode (fail-safe)

---

## Testing the Setup

### 1. Basic Connectivity Test

```bash
# In Claude Desktop or other client:
search_tools "file"

# Should return:
# • read_file [SAFE]
#   Read file contents from workspace.
#
# • write_file [SENSITIVE]
#   Write content to file in workspace.
# ...
```

### 2. Read Operation Test (Non-Sensitive)

```bash
list_directory "."

# Should return:
# [DIR]  config/
# [DIR]  src/
# [FILE] README.md (1234 bytes)
# ...
```

### 3. Write Operation Test (Sensitive, Requires Approval)

```bash
write_file "test.txt" "Hello from MCP!"

# Should trigger approval request:
# # Approval Required
# **Tool:** `write_file`
# **Arguments:**
# - `path`: test.txt
# - `content`: Hello from MCP!
#
# Type 'approve' to execute or 'deny' to reject
```

### 4. Admin Operation Test

```bash
get_governance_status

# Should return:
# # Governance System Status
# **Mode:** `permission`
# **Active Elevations:** 0
# ...
```

---

## Advanced Configuration

### Custom Meta-Supervisor Port

If running meta-supervisor on a different port:

```json
{
  "mcpServers": {
    "MetaSupervisor": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--streamableHttp",
        "http://localhost:9000/mcp"  // Custom port
      ]
    }
  }
}
```

### Remote Meta-Supervisor

To connect to a remote meta-supervisor instance:

```json
{
  "mcpServers": {
    "MetaSupervisor": {
      "command": "npx",
      "args": [
        "-y",
        "supergateway",
        "--streamableHttp",
        "http://remote-server.example.com:8001/mcp"
      ]
    }
  }
}
```

**Security Note:** Ensure the remote server has proper authentication and TLS!

---

## Security Best Practices

1. **Never expose meta-supervisor publicly without authentication**
   - Run behind VPN or firewall
   - Use TLS for remote connections
   - Implement authentication middleware

2. **Monitor audit logs regularly**
   ```bash
   tail -f audit.jsonl | jq -r '[.timestamp, .event, .tool_name] | @tsv'
   ```

3. **Use READ_ONLY mode for untrusted environments**
   ```bash
   set_governance_mode "read_only"
   ```

4. **Rotate API keys regularly**
   - Update .env file
   - Restart Docker containers

5. **Review governance mode periodically**
   ```bash
   get_governance_status
   ```

---

## Next Steps

1. **Configure your preferred client** using the examples above
2. **Test basic operations** with the connectivity tests
3. **Explore governance features** by testing sensitive operations
4. **Review audit logs** to understand what's being tracked
5. **Set up monitoring** for production use

For more information, see:
- [Meta-Supervisor Documentation](../README.md)
- [FastMCP Documentation](https://github.com/modelcontextprotocol/fastmcp)
- [supergateway Repository](https://github.com/modelcontextprotocol/supergateway)
