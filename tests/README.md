# MetaMCP+ Test Suite Documentation

## Overview
The MetaMCP+ test suite exercises the core discovery, governance, lease, and registry systems.
It includes unit tests for individual modules, integration tests for end-to-end flows, and
security tests that validate governance constraints and schema exposure rules.

## Test Organization

### Directory Structure
```
tests/
├── conftest.py              # Shared fixtures
├── test_utils.py            # Utility functions
├── test_*.py                # Unit tests
├── integration/             # Integration tests
│   ├── test_full_discovery_flow.py
│   ├── test_lease_governance_flow.py
│   ├── test_notification_flow.py
│   └── test_end_to_end_scenario.py
└── README.md               # This file
```

### Test Categories
- **Registry Tests** (`test_registry.py`, `test_registry_models.py`) - Tool registration, search
- **Lease Tests** (`test_lease_*.py`) - Lease lifecycle, security
- **Governance Tests** (`test_governance_*.py`) - Modes, policies, tokens
- **Schema Tests** (`test_schema_*.py`) - Minimization, expansion, leakage protection
- **Notification Tests** (`test_list_changed_emission.py`, `test_notifications.py`) - list_changed behavior
- **Integration Tests** (`integration/`) - Full workflows

## Running Tests

### All Tests
```bash
pytest tests/ -v
```

### Specific Test File
```bash
pytest tests/test_registry.py -v
```

### Specific Test
```bash
pytest tests/test_registry.py::test_bootstrap_tools_defined -v
```

### By Marker
```bash
pytest tests/ -v -m "not slow"
pytest tests/ -v -m integration
pytest tests/ -v -m requires_redis
```

### With Coverage
```bash
pytest tests/ --cov=src/meta_mcp --cov-report=html
```

## Common Fixtures

### Lease Fixtures (conftest.py)
- `lease_for_tool` - Grant single lease for testing

Usage:
```python
async def test_something(lease_for_tool):
    await lease_for_tool("write_file")
```

### Governance Fixtures
- `governance_in_read_only` - Sets READ_ONLY mode for a test
- `governance_in_permission` - Sets PERMISSION mode for a test
- `governance_in_bypass` - Sets BYPASS mode for a test

### Audit Fixtures
- `audit_log_path` - Creates isolated audit log path
- `read_audit_log` - Reads JSONL audit entries

## Writing New Tests

### Test File Template
```python
"""Tests for [component]."""

import pytest
from src.meta_mcp.[module] import [component]

@pytest.mark.asyncio
class Test[Component]:
    """Test suite for [component]."""

    async def test_basic_functionality(self):
        """[Component] should do X when Y."""
        # Arrange
        ...

        # Act
        result = await component.method()

        # Assert
        assert result == expected
```

### Test Naming Conventions
- Test files: `test_<module>.py`
- Test classes: `Test<Component>`
- Test methods: `test_<what>_<when>_<expected>`

Examples:
- `test_lease_consumed_when_tool_executed`
- `test_governance_blocks_when_read_only_mode`
- `test_search_returns_relevant_results`

### Assertion Patterns

**Good:**
```python
assert result["success"] is True, "Expected successful execution"
assert "error" not in result, f"Unexpected error: {result.get('error')}"
```

**Bad:**
```python
assert result  # Unclear what's being tested
assert True    # Useless assertion
```

## Test Utilities

See `test_utils.py` for shared utilities:
- `create_test_tool()` - Create tool records
- `create_test_registry()` - Populate registry with tools
- `assert_audit_log_contains()` - Verify audit logging
- `mock_fastmcp_context()` - Mock FastMCP contexts
- `cleanup_test_files()` - File cleanup
- `wait_for_condition()` - Async condition polling

## Markers

Custom pytest markers registered in `conftest.py`:
- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.requires_redis` - Test requires Redis
- `@pytest.mark.requires_api_keys` - Test requires API keys
- `@pytest.mark.skip(reason="...")` - Skip test

## Troubleshooting

### Tests Fail with "No lease"
Grant lease first using `lease_for_tool` fixture:
```python
async def test_something(lease_for_tool):
    await lease_for_tool("tool_name")
```

### Tests Fail with "Tool not in registry"
Use a test registry and add tools via `create_test_tool()`:
```python
from tests.test_utils import create_test_registry, create_test_tool

registry = create_test_registry([create_test_tool("my_tool")])
```

### Async Tests Hang
Ensure test marked with `@pytest.mark.asyncio`:
```python
@pytest.mark.asyncio
async def test_something():
    await some_async_function()
```

### Redis Connection Errors
Ensure Redis running (`redis-server`) or use `@pytest.mark.requires_redis` to allow auto-skip.

## Best Practices

1. **Test One Thing** - Each test should validate one behavior
2. **Arrange-Act-Assert** - Structure tests clearly
3. **Descriptive Names** - Test names should explain what's tested
4. **Use Fixtures** - Avoid duplicated setup
5. **Clean Up** - Use fixtures/utilities for cleanup
6. **Async Properly** - Mark async tests, await async calls
7. **Assert Messages** - Include helpful assertion messages
8. **Test Edge Cases** - Test more than the happy path

## Continuous Integration

Tests run automatically on:
- Every commit (fast tests)
- Pull requests (full suite)
- Nightly (full suite + slow tests)

CI configuration: `.github/workflows/test.yml`

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
