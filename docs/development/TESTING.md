# Testing Guide

## Overview

The MetaServer test suite is organized into categories to support both local development and CI/CD environments with varying infrastructure availability.

## Test Categories

### Unit Tests (`-m unit`)

**Characteristics:**
- Fast execution (< 5 seconds total)
- No external dependencies (no Redis, APIs, databases)
- Test pure business logic, data models, configuration
- Should always pass in any environment

**Example:**
```python
@pytest.mark.unit
def test_config_validation():
    assert Config.validate() is True
```

**Run unit tests:**
```bash
pytest -m unit
```

### Integration Tests (`-m integration`)

**Characteristics:**
- Require external services (Redis, APIs, etc.)
- Test interaction between components
- May fail in environments without proper setup
- Located in `tests/integration/`

**Example:**
```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_workflow(redis_client):
    # Test lease manager with real Redis
    ...
```

**Run integration tests:**
```bash
# Ensure Redis is running first
docker run -d -p 6379:6379 redis:7-alpine

pytest -m integration
```

### Tests by Dependency

**Redis-dependent tests (`-m requires_redis`):**
- Automatically skipped when Redis is unavailable
- Include governance, lease management, caching tests

**API-dependent tests (`-m requires_api_keys`):**
- Automatically skipped when API keys are not configured
- Include LLM integration, external service tests

## Quick Start

### Install Dependencies

```bash
# Install with dev dependencies
pip install -e ".[dev]"
```

### Run All Unit Tests (No Setup Required)

```bash
pytest -m unit
```

Expected output:
```
56 passed, 406 deselected in 3.35s
```

### Run All Tests (Requires Redis)

```bash
# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Run all tests
pytest
```

### Run Specific Test Files

```bash
# Unit tests for configuration
pytest tests/test_config.py -v

# Integration tests for leases
pytest tests/integration/test_lease_governance_flow.py -v
```

### Run Tests Without Redis

The test suite will automatically skip Redis-dependent tests when Redis is unavailable:

```bash
pytest
```

You'll see warnings:
```
⚠️  Test Environment Warnings:
  - Redis not available - Redis-dependent tests will be skipped
```

And skipped tests:
```
102 tests skipped (Redis not available)
```

## CI/CD Behavior

The GitHub Actions workflow runs tests in stages:

### 1. Unit Tests (Blocking)

```bash
pytest -m "unit" -v --tb=short --maxfail=10
```

- **Must pass** for PR approval
- Failures indicate bugs in the PR
- Exit code determines overall workflow success

### 2. Integration Tests (Informational)

```bash
pytest -m "integration or requires_redis or requires_api_keys" -v --tb=short --maxfail=5
```

- May fail due to missing API keys/services in CI
- Failures don't block merge if unit tests pass
- Review output to distinguish PR bugs from environment issues

### 3. Other Tests (Informational)

```bash
pytest -m "not unit and not integration" -v --tb=short --maxfail=5
```

- Miscellaneous tests
- Failures may be environment-related

### Workflow Verdicts

The workflow reports one of three verdicts:

- 🟢 **READY FOR MERGE** - All tests passing
- 🟡 **REVIEW REQUIRED** - Unit tests pass, integration tests failed (likely environmental)
- 🔴 **BLOCKED** - Unit tests failing (PR needs fixes)

## Writing New Tests

### For Unit Tests

```python
import pytest

@pytest.mark.unit
def test_pure_logic():
    """Test business logic without external dependencies."""
    result = some_function(input_data)
    assert result == expected_output
```

### For Integration Tests (with Redis)

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_with_redis(redis_client):
    """Test component interaction with Redis."""
    # Test will be skipped if Redis is unavailable
    await redis_client.set("key", "value")
    result = await redis_client.get("key")
    assert result == "value"
```

### For Tests Requiring API Keys

```python
import pytest
import os

@pytest.mark.integration
@pytest.mark.requires_api_keys
async def test_with_api():
    """Test API integration."""
    # Test will be skipped if API keys are not configured
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    # ... test logic
```

## Troubleshooting

### All Integration Tests Skipped

**Cause:** Redis is not running

**Solution:**
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### Tests Fail with "Connection refused"

**Cause:** Redis started but not ready

**Solution:** Wait a few seconds and re-run

### Unit Tests Failing

**Cause:** Actual bugs in the code (unit tests should always pass)

**Solution:** Fix the code - unit test failures are always blocking

### Integration Tests Failing in CI

**Cause:** May be expected if CI lacks API keys or specific services

**Solution:** 
1. Check if unit tests pass (if yes, PR may still be fine)
2. Review failure output to determine if it's environmental or a real bug
3. If environmental, document in PR and proceed with review

## Test Coverage

Generate coverage report:

```bash
pytest --cov=src --cov=MetaServer --cov-report=html
open htmlcov/index.html
```

## Best Practices

1. **Always mark tests appropriately**: Use `@pytest.mark.unit`, `@pytest.mark.integration`, and `@pytest.mark.requires_redis` as needed
2. **Unit tests should be fast**: < 100ms per test ideally
3. **Integration tests should clean up**: Use fixtures that flush Redis, reset state
4. **Don't hardcode paths**: Use `tmp_path` fixture or `Path` objects
5. **Use async fixtures for async tests**: Ensure `@pytest.mark.asyncio` is present
6. **Test one thing per test**: Keep tests focused and atomic

## Examples

### Good Unit Test
```python
@pytest.mark.unit
def test_lease_model_validation():
    """Test ToolLease validation logic."""
    with pytest.raises(ValueError):
        ToolLease.create(
            client_id="test",
            tool_id="read_file",
            ttl_seconds=0,  # Invalid
            calls_remaining=1,
            mode_at_issue="PERMISSION",
        )
```

### Good Integration Test
```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_grant_and_consume(redis_client, lease_for_tool):
    """Test complete lease lifecycle."""
    # Grant lease
    await lease_for_tool("read_file", calls=3)
    
    # Consume lease
    from src.meta_mcp.leases import lease_manager
    success = await lease_manager.consume("test-session-123", "read_file")
    assert success is True
    
    # Verify calls decremented
    lease = await lease_manager.get("test-session-123", "read_file")
    assert lease.calls_remaining == 2
```

## Summary

- **Unit tests** = Fast, no dependencies, always pass → Blocking in CI
- **Integration tests** = Require services, may fail → Informational in CI
- **Auto-skip** = Tests gracefully skip when dependencies unavailable
- **Smart CI** = Only unit test failures block merge

This approach ensures reliable CI/CD while maintaining comprehensive test coverage when infrastructure is available.
