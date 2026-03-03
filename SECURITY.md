# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in MetaServer, please report it responsibly:

1. **Do NOT open a public issue.**
2. Email **[security contact — owner to fill in]** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
3. You will receive an acknowledgment within 48 hours.
4. A fix will be developed privately and released as a patch.

## Security Architecture

MetaServer implements defense-in-depth governance:

- **Tri-state governance modes** (read_only, permission, bypass) enforced via Redis-backed state
- **Per-session cryptographic keys** — one-time-use keys with automatic rotation after each mode change
- **HMAC-signed capability tokens** with mandatory TTL for tool elevation
- **Lease-based access control** — time-bounded tool access with automatic expiration
- **Audit logging** — all governance decisions, mode changes, and key rotations are logged
- **Fail-safe defaults** — if key setup fails, server locks to `permission` mode with changes disabled

### Key Storage
- Governance session keys are written to disk with `0o400` (owner-read-only) permissions
- Only the SHA-256 hash of the active key is stored in Redis — the raw key never touches Redis
- Keys are rotated after each successful use and cleaned up on shutdown
