# Security Test Coverage Matrix

## Threat Model Summary

MetaMCP Server protects privileged tool execution, leases, and governance decisions. The
security posture depends on strict scope enforcement, lease validation, and human-in-the-loop
approval integrity. Primary assets and risks:

- **Assets**: tool registry, lease state (Redis), approval decisions, audit logs, and scoped
  elevation grants.
- **Attack surfaces**: tool invocation middleware, approval provider interface, lease validation,
  registry mutations during tests, and audit logging paths.
- **Assumptions**: Redis is authoritative for leases, approval providers return structured
  responses, and test suites must not leak global state between runs.

## Coverage Matrix (Threats → Tests)

| Threat Scenario | STRIDE | DREAD Notes | Key Tests |
| --- | --- | --- | --- |
| Unauthorized tool execution without lease | Elevation of Privilege | High impact, high reproducibility | `tests/test_lease_security.py`, `tests/test_lease_manager.py` |
| Lease replay or stale lease reuse | Spoofing / Tampering | Moderate impact, high reproducibility | `tests/test_lease_manager.py`, `tests/test_lease_models.py` |
| Scope escalation via missing resource scope | Elevation of Privilege | High impact, moderate detectability | `tests/test_scoped_elevation.py`, `tests/test_elicitation.py` |
| Approval spoofing or malformed response | Spoofing / Tampering | High impact, high reproducibility | `tests/test_elicitation.py`, `tests/test_fail_safe.py` |
| Approval timeout bypass | Denial of Service / EoP | High impact, medium exploitability | `tests/test_elicitation.py` |
| Registry mutation leaking across tests | Tampering | Medium impact, high reproducibility | `tests/test_semantic_search.py` (registry isolation) |
| Audit log omission for approvals | Repudiation | High impact, high detectability | `tests/test_elicitation.py`, `tests/test_audit_fixes.py` |
| Progressive discovery leakage | Information Disclosure | High impact, medium exploitability | `tests/test_progressive_discovery.py`, `tests/test_visibility_rules.py` |
| Token misuse for tool access | Spoofing | High impact, medium exploitability | `tests/test_capability_tokens.py`, `tests/test_token_security.py` |

## STRIDE/DREAD Analysis Highlights

| STRIDE Category | Typical Threat | Example Tests | DREAD Notes |
| --- | --- | --- | --- |
| Spoofing | Fake approval/lease | `tests/test_elicitation.py`, `tests/test_lease_security.py` | High damage, high reproducibility |
| Tampering | Registry or lease mutation | `tests/test_semantic_search.py`, `tests/test_lease_manager.py` | Medium damage, high reproducibility |
| Repudiation | Missing audit trails | `tests/test_elicitation.py`, `tests/test_audit_fixes.py` | High damage, high detectability |
| Information Disclosure | Tool/schema leakage | `tests/test_schema_leakage.py`, `tests/test_visibility_rules.py` | High damage, medium reproducibility |
| Denial of Service | Approval timeout abuse | `tests/test_elicitation.py` | Medium damage, medium reproducibility |
| Elevation of Privilege | Scope expansion or lease bypass | `tests/test_scoped_elevation.py`, `tests/test_lease_security.py` | High damage, high exploitability |

## Gaps & Follow-ups

- Expand approval provider fidelity tests when new providers are added.
- Add explicit performance regression checks once latency baselines are finalized.
- Track new governance state transitions in audit coverage when modes expand.
