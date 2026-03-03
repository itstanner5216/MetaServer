"""Tests for per-session governance bypass keys."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.meta_mcp import supervisor as supervisor_module
from src.meta_mcp.config import Config
from src.meta_mcp.governance.session_key import (
    GOVERNANCE_SESSION_KEY_HASH,
    GovernanceKeyManager,
)
from src.meta_mcp.state import ExecutionMode, GovernanceState


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


def test_key_generation_is_random():
    assert GovernanceKeyManager.generate_key() != GovernanceKeyManager.generate_key()


def test_key_file_written_with_restrictive_permissions(tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    path = manager.write_key("a" * 64)
    assert path.stat().st_mode & 0o777 == 0o400


def test_key_file_written_to_configured_directory(tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    path = manager.write_key("b" * 64)
    assert path.parent == tmp_path


@pytest.mark.asyncio
async def test_set_mode_requires_valid_key(monkeypatch):
    state = GovernanceState()
    redis = FakeRedis()
    monkeypatch.setattr(state, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(state._key_manager, "validate_and_rotate", AsyncMock(return_value=False))  # noqa: SLF001

    with pytest.raises(PermissionError, match="Invalid governance session key"):
        await state.set_mode(ExecutionMode.BYPASS, "wrong")


@pytest.mark.asyncio
async def test_set_mode_with_valid_key_succeeds(monkeypatch):
    state = GovernanceState()
    redis = FakeRedis()
    monkeypatch.setattr(state, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(state._key_manager, "validate_and_rotate", AsyncMock(return_value=True))  # noqa: SLF001

    assert await state.set_mode(ExecutionMode.BYPASS, "valid") is True
    assert redis.store["governance:mode"] == "bypass"


@pytest.mark.asyncio
async def test_key_rotated_after_use(tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    redis = FakeRedis()
    await manager.initialize(redis)
    old_key = manager.key_path.read_text().strip()

    assert await manager.validate_and_rotate(old_key, redis) is True
    assert await manager.validate_and_rotate(old_key, redis) is False


@pytest.mark.asyncio
async def test_new_key_written_after_rotation(tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    redis = FakeRedis()
    await manager.initialize(redis)
    old_key = manager.key_path.read_text().strip()

    await manager.validate_and_rotate(old_key, redis)
    assert manager.key_path.read_text().strip() != old_key


@pytest.mark.asyncio
async def test_constant_time_comparison(monkeypatch, tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    redis = FakeRedis()
    await manager.initialize(redis)

    called = {"value": False}

    def _fake_compare(a, b):
        called["value"] = True
        return True

    monkeypatch.setattr("src.meta_mcp.governance.session_key.hmac.compare_digest", _fake_compare)
    await manager.validate_and_rotate("anything", redis)
    assert called["value"] is True


@pytest.mark.asyncio
async def test_key_hash_stored_in_redis_not_raw(tmp_path):
    manager = GovernanceKeyManager(str(tmp_path))
    redis = FakeRedis()
    path = await manager.initialize(redis)

    raw_key = path.read_text().strip()
    stored_hash = redis.store[GOVERNANCE_SESSION_KEY_HASH]
    assert stored_hash != raw_key
    assert stored_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_startup_generates_key(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "WORKSPACE_ROOT", str(tmp_path / "workspace"))

    key_path = tmp_path / "keys" / "governance.key"

    async def _init_key():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("abc", encoding="utf-8")
        return str(key_path)

    monkeypatch.setattr(supervisor_module.governance_state, "initialize_session_key", _init_key)
    monkeypatch.setattr(supervisor_module, "check_redis_health", AsyncMock(return_value=(True, "ok")))
    monkeypatch.setattr(
        supervisor_module.governance_state,
        "get_mode",
        AsyncMock(return_value=ExecutionMode.PERMISSION),
    )
    monkeypatch.setattr(supervisor_module, "run_all_validations", AsyncMock())

    provider = AsyncMock()
    provider.is_available.return_value = True
    provider.get_name.return_value = "test"
    monkeypatch.setattr(supervisor_module, "get_approval_provider", AsyncMock(return_value=provider))
    monkeypatch.setattr(
        supervisor_module,
        "get_artifact_generator",
        lambda: type("A", (), {"artifacts_root": tmp_path})(),
    )

    async with supervisor_module.lifespan(None):
        assert key_path.exists()


@pytest.mark.asyncio
async def test_shutdown_cleans_key_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "WORKSPACE_ROOT", str(tmp_path / "workspace"))

    key_path = tmp_path / "keys" / "governance.key"

    async def _init_key():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("abc", encoding="utf-8")
        return str(key_path)

    monkeypatch.setattr(supervisor_module.governance_state, "initialize_session_key", _init_key)
    monkeypatch.setattr(
        supervisor_module.governance_state,
        "cleanup_session_key",
        lambda: key_path.unlink(missing_ok=True),
    )
    monkeypatch.setattr(supervisor_module, "check_redis_health", AsyncMock(return_value=(True, "ok")))
    monkeypatch.setattr(
        supervisor_module.governance_state,
        "get_mode",
        AsyncMock(return_value=ExecutionMode.PERMISSION),
    )
    monkeypatch.setattr(supervisor_module, "run_all_validations", AsyncMock())

    provider = AsyncMock()
    provider.is_available.return_value = True
    provider.get_name.return_value = "test"
    monkeypatch.setattr(supervisor_module, "get_approval_provider", AsyncMock(return_value=provider))
    monkeypatch.setattr(
        supervisor_module,
        "get_artifact_generator",
        lambda: type("A", (), {"artifacts_root": tmp_path})(),
    )

    async with supervisor_module.lifespan(None):
        assert key_path.exists()

    assert not key_path.exists()


@pytest.mark.asyncio
async def test_invalid_key_attempt_is_audited(monkeypatch):
    state = GovernanceState()
    redis = FakeRedis()
    monkeypatch.setattr(state, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(state._key_manager, "validate_and_rotate", AsyncMock(return_value=False))  # noqa: SLF001

    log_mock = MagicMock()
    monkeypatch.setattr("src.meta_mcp.state.audit_logger.log", log_mock)

    with pytest.raises(PermissionError):
        await state.set_mode(ExecutionMode.BYPASS, "bad")

    assert log_mock.call_args.args[0].value == "governance_mode_change_denied"


@pytest.mark.asyncio
async def test_successful_mode_change_is_audited(monkeypatch):
    state = GovernanceState()
    redis = FakeRedis()
    monkeypatch.setattr(state, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(state._key_manager, "validate_and_rotate", AsyncMock(return_value=True))  # noqa: SLF001

    log_mock = MagicMock()
    monkeypatch.setattr("src.meta_mcp.state.audit_logger.log", log_mock)

    await state.set_mode(ExecutionMode.BYPASS, "valid")

    events = [call.args[0].value for call in log_mock.call_args_list]
    assert "governance_mode_change" in events


@pytest.mark.asyncio
async def test_default_governance_mode_only_cold_start(monkeypatch):
    state = GovernanceState()
    redis = FakeRedis()
    monkeypatch.setattr(state, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(Config, "DEFAULT_EXECUTION_MODE", "bypass")

    assert await state.get_mode() == ExecutionMode.BYPASS

    redis.store["governance:mode"] = "read_only"
    monkeypatch.setattr(Config, "DEFAULT_EXECUTION_MODE", "permission")
    assert await state.get_mode() == ExecutionMode.READ_ONLY
