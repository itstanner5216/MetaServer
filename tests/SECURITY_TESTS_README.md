# Security Test Files for Phase 3 & 4

This directory contains comprehensive security test files for future MetaMCP+ phases. These tests are currently **skipped** and will be enabled as implementation progresses.

## Overview

Created: 2025-12-30
Purpose: Ensure security-critical functionality is validated before Phase 3 and 4 are considered complete.

## Test Files

### Phase 3 (Lease Manager) - CRITICAL SECURITY

#### 1. `test_lease_security.py` - **MUST PASS 100%**
Critical security tests that validate the lease system prevents:
- Cross-session lease leakage
- Expired lease acceptance
- Bootstrap tool lockout
- Lease consumption on failure
- Missing client_id bypass

**Tests:**
- `test_cross_session_isolation()` - CRITICAL: Prevents privilege escalation
- `test_lease_expiration()` - CRITICAL: Enforces time boundaries
- `test_bootstrap_tools_skip_lease_check()` - CRITICAL: Prevents infinite loop
- `test_lease_consumption_only_on_success()` - CRITICAL: Prevents DoS
- `test_lease_not_granted_without_client_id()` - CRITICAL: Enforces scoping
- `test_calls_remaining_decrements_correctly()` - Lifecycle validation
- `test_lease_revocation()` - Emergency controls
- `test_lease_ttl_enforced()` - Redis TTL validation
- `test_lease_mode_consistency()` - Mode change handling
- `test_multiple_leases_per_session()` - Storage key uniqueness
- `test_lease_fail_closed_on_redis_error()` - CRITICAL: Fail-safe behavior

#### 2. `test_lease_models.py`
Unit tests for ToolLease dataclass:
- Creation and validation
- Expiration logic
- Consumption tracking
- Serialization for Redis storage

#### 3. `test_lease_manager.py`
Unit tests for LeaseManager methods:
- `grant()` - Create new leases
- `validate()` - Check lease validity
- `consume()` - Decrement lease calls
- `revoke()` - Delete leases
- `purge()` - Cleanup expired leases

### Phase 4 (Governance Engine) - CRITICAL SECURITY

#### 4. `test_token_security.py` - **MUST PASS 100%**
Critical security tests for capability tokens:
- Token forgery prevention (HMAC verification)
- Token expiration enforcement
- Token replay prevention
- Payload tampering detection
- Client/tool binding validation

**Tests:**
- `test_token_forgery_rejected()` - CRITICAL: #1 security test
- `test_expired_token_rejected()` - CRITICAL: Prevents replay
- `test_token_replay_prevention()` - CRITICAL: One-time use
- `test_invalid_signature_rejected()` - CRITICAL: Tamper detection
- `test_token_canonicalization_deterministic()` - Consistency
- `test_token_client_id_binding()` - CRITICAL: Session binding
- `test_token_tool_id_binding()` - CRITICAL: Tool binding
- `test_hmac_secret_not_empty()` - CRITICAL: Configuration check
- `test_token_contains_required_fields()` - Payload structure
- `test_token_with_context_key()` - Additional scoping
- `test_malformed_token_rejected()` - Error handling
- `test_token_generation_performance()` - Performance check

#### 5. `test_schema_leakage.py` - **MUST PASS 100%**
Prevents schema information disclosure:
- Blocked tools must not return schemas
- Approval requests must not include schemas
- Error messages must not leak schema details

**Tests:**
- `test_blocked_tool_no_schema()` - CRITICAL: No reconnaissance
- `test_approval_required_no_schema()` - CRITICAL: Pre-approval leak
- `test_schema_only_after_lease_grant()` - Positive case
- `test_schema_minimal_before_expansion()` - Phase 5 integration
- `test_error_message_no_schema_leak()` - Error handling
- `test_search_results_no_schema()` - Progressive discovery
- `test_bootstrap_tools_schema_always_available()` - Bootstrap exception
- `test_schema_stripped_from_denial_response()` - Response construction
- `test_partial_schema_leak_in_json()` - Deep inspection
- `test_schema_not_in_logs()` - Logging safety

#### 6. `test_governance_integration.py`
Integration tests for governance + leases:
- Governance check before lease grant
- Token verification at call time
- Mode-based tool blocking
- Policy matrix enforcement

#### 7. `test_capability_tokens.py`
Unit tests for token operations:
- `generate_token()` - Create signed tokens
- `verify_token()` - Signature + expiration check
- `decode_token()` - Payload extraction
- HMAC-SHA256 implementation

#### 8. `test_policy_engine.py`
Unit tests for governance policy matrix:
- Mode + Risk → Decision mapping
- Bootstrap tool exceptions
- Unknown risk fail-safe

## Running Tests

### All security tests (currently skipped):
```bash
pytest tests/test_lease_security.py -v
pytest tests/test_token_security.py -v
pytest tests/test_schema_leakage.py -v
```

Expected output: "X skipped" (not "X failed")

### After Phase 3 implementation:
```bash
# Remove skip marker from test_lease_security.py
pytest tests/test_lease_security.py -v
# ALL TESTS MUST PASS before Phase 3 is complete
```

### After Phase 4 implementation:
```bash
# Remove skip markers from Phase 4 test files
pytest tests/test_token_security.py -v
pytest tests/test_schema_leakage.py -v
pytest tests/test_governance_integration.py -v
# ALL TESTS MUST PASS before Phase 4 is complete
```

## Success Criteria

### Phase 3 Complete When:
✅ All tests in `test_lease_security.py` pass (100%)
✅ All tests in `test_lease_models.py` pass
✅ All tests in `test_lease_manager.py` pass
✅ No regressions in existing progressive discovery tests
✅ Bootstrap tools accessible without leases
✅ Cross-session isolation verified

### Phase 4 Complete When:
✅ All tests in `test_token_security.py` pass (100%)
✅ All tests in `test_schema_leakage.py` pass (100%)
✅ All tests in `test_governance_integration.py` pass
✅ All tests in `test_capability_tokens.py` pass
✅ All tests in `test_policy_engine.py` pass
✅ Token forgery test passes (critical)
✅ No schema leakage in any scenario

## Critical Security Tests

These tests MUST NEVER be skipped or disabled in production:

1. **test_cross_session_isolation** - Prevents privilege escalation
2. **test_token_forgery_rejected** - Prevents governance bypass
3. **test_blocked_tool_no_schema** - Prevents reconnaissance
4. **test_lease_fail_closed_on_redis_error** - Fail-safe validation
5. **test_token_replay_prevention** - Prevents token reuse

If any of these fail, **STOP implementation immediately** and fix before proceeding.

## Implementation Notes

### TODO Comments
Each test includes TODO comments showing:
- What imports are needed
- What assertions to make
- What security risks are being tested

Example:
```python
# TODO: Import after Phase 3
# from src.meta_mcp.leases import lease_manager
```

### Security Risk Documentation
Every test includes a docstring explaining:
- What security risk is being tested
- What attack scenario is prevented
- Why this test is critical

### Test-Driven Development
These tests define the security contract. Implementation should:
1. Enable one test file at a time
2. Implement functionality to pass tests
3. Verify all tests pass before moving on
4. NEVER skip a failing security test

## Reference Documents

- `/home/tanner/Projects/MCPServer/.MCP/IMPLEMENTATION_BLUEPRINT.md` - Section 7 (Testing Strategy)
- `/home/tanner/Projects/MCPServer/.MCP/DEVELOPER_REFERENCE.md` - Nuances to test
- `.MCP/ARCHITECTURE_INTEGRATION_MAP.md` - Integration points

## Maintenance

When modifying these tests:
1. Keep security risk documentation updated
2. Add new attack scenarios as discovered
3. Never remove a security test without documented justification
4. Update this README when adding new test files

## Questions?

See Implementation Blueprint Section 3 (Phase 3) and Section 4 (Phase 4) for detailed requirements.
