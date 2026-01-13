"""Tests for centralized Config class."""
import importlib
import warnings

import pytest

from src.meta_mcp import config as config_module
from src.meta_mcp.config import Config


def _reload_config(monkeypatch, **env):
    for key in ("DEFAULT_GOVERNANCE_MODE", "DEFAULT_MODE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config_module).Config


def test_config_defaults():
    """Verify default configuration values."""
    assert Config.HOST == "0.0.0.0"
    assert Config.PORT == 8001
    assert Config.DEFAULT_ELEVATION_TTL == 300
    assert Config.ELICITATION_TIMEOUT == 300
    assert Config.WORKSPACE_ROOT == "./workspace"


def test_config_lease_ttl_positive():
    """All lease TTLs must be > 0 (Nuance 2.8)."""
    for risk, ttl in Config.LEASE_TTL_BY_RISK.items():
        assert ttl > 0, f"TTL for {risk} must be positive, got {ttl}"


def test_config_lease_calls_positive():
    """All lease call counts must be >= 0."""
    for risk, calls in Config.LEASE_CALLS_BY_RISK.items():
        assert calls >= 0, f"Calls for {risk} must be non-negative, got {calls}"


def test_config_validation_with_ttl():
    """Config.validate() should pass when all TTLs are positive."""
    # Save original values
    original_ttl = Config.DEFAULT_ELEVATION_TTL
    original_timeout = Config.ELICITATION_TIMEOUT

    try:
        # Set valid values
        Config.DEFAULT_ELEVATION_TTL = 300
        Config.ELICITATION_TIMEOUT = 300

        # Should not raise
        assert Config.validate() is True
    finally:
        # Restore originals
        Config.DEFAULT_ELEVATION_TTL = original_ttl
        Config.ELICITATION_TIMEOUT = original_timeout


def test_config_validation_fails_on_zero_ttl():
    """Config.validate() should fail if any TTL is <= 0."""
    # Save original value
    original_ttl = Config.DEFAULT_ELEVATION_TTL

    try:
        # Set invalid value
        Config.DEFAULT_ELEVATION_TTL = 0

        # Should raise ValueError
        with pytest.raises(ValueError, match="DEFAULT_ELEVATION_TTL must be > 0"):
            Config.validate()
    finally:
        # Restore original
        Config.DEFAULT_ELEVATION_TTL = original_ttl


def test_config_validation_fails_on_negative_ttl():
    """Config.validate() should fail if any TTL is negative."""
    # Save original value
    original_ttl = Config.ELICITATION_TIMEOUT

    try:
        # Set invalid value
        Config.ELICITATION_TIMEOUT = -1

        # Should raise ValueError
        with pytest.raises(ValueError, match="ELICITATION_TIMEOUT must be > 0"):
            Config.validate()
    finally:
        # Restore original
        Config.ELICITATION_TIMEOUT = original_ttl


def test_config_redis_url():
    """Redis URL should be set with default."""
    assert Config.REDIS_URL == "redis://localhost:6379"


def test_config_feature_flags_default_disabled():
    """Feature flags should default to disabled (Nuance 2.7 - fail-safe)."""
    assert Config.ENABLE_SEMANTIC_RETRIEVAL is False
    # Phase 3 and Phase 7 flags are now enabled for testing
    assert Config.ENABLE_LEASE_MANAGEMENT is True
    assert Config.ENABLE_PROGRESSIVE_SCHEMAS is False
    assert Config.ENABLE_MACROS is True


def test_default_execution_mode_env_keys(monkeypatch):
    """Default execution mode should map from new and deprecated keys."""
    config = _reload_config(monkeypatch, DEFAULT_GOVERNANCE_MODE="read_only")
    assert config.DEFAULT_EXECUTION_MODE == "read_only"

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        config = _reload_config(monkeypatch, DEFAULT_MODE="bypass")
        assert config.DEFAULT_EXECUTION_MODE == "bypass"
        assert any(
            "DEFAULT_MODE is deprecated" in str(warning.message)
            for warning in captured
        )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        config = _reload_config(
            monkeypatch,
            DEFAULT_GOVERNANCE_MODE="permission",
            DEFAULT_MODE="read_only",
        )
        assert config.DEFAULT_EXECUTION_MODE == "permission"
        assert any(
            "DEFAULT_MODE is deprecated" in str(warning.message)
            for warning in captured
        )
