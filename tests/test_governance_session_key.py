import hashlib

import pytest
from unittest.mock import AsyncMock, patch

from src.meta_mcp.config import Config
from src.meta_mcp.governance.session_key import GovernanceKeyManager
from src.meta_mcp.state import ExecutionMode, GovernanceState


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value
        return True


@pytest.mark.asyncio
async def test_key_generation_is_random():
    manager = GovernanceKeyManager(FakeRedis())
    assert manager.generate_key() != manager.generate_key()


@pytest.mark.asyncio
async def test_key_file_written_with_restrictive_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    manager = GovernanceKeyManager(FakeRedis())
    path = manager.write_key(manager.generate_key())
    assert path.stat().st_mode & 0o777 == 0o400


@pytest.mark.asyncio
async def test_key_file_written_to_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    manager = GovernanceKeyManager(FakeRedis())
    key = manager.generate_key()
    path = manager.write_key(key)
    assert path == tmp_path / "governance.key"
    assert path.read_text(encoding="utf-8") == key


@pytest.mark.asyncio
async def test_set_mode_requires_valid_key(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    with pytest.raises(PermissionError, match="Invalid governance session key"):
        await state.set_mode(ExecutionMode.BYPASS, session_key="wrong-key")


@pytest.mark.asyncio
async def test_set_mode_with_valid_key_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    path = await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    key = path.read_text(encoding="utf-8")
    changed = await state.set_mode(ExecutionMode.READ_ONLY, session_key=key)

    assert changed is True
    assert await state.get_mode() == ExecutionMode.READ_ONLY


@pytest.mark.asyncio
async def test_key_rotated_after_use(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    path = await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    old_key = path.read_text(encoding="utf-8")
    await state.set_mode(ExecutionMode.READ_ONLY, session_key=old_key)
    with pytest.raises(PermissionError):
        await state.set_mode(ExecutionMode.PERMISSION, session_key=old_key)


@pytest.mark.asyncio
async def test_new_key_written_after_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    path = await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    old_key = path.read_text(encoding="utf-8")
    await state.set_mode(ExecutionMode.BYPASS, session_key=old_key)
    assert path.read_text(encoding="utf-8") != old_key


@pytest.mark.asyncio
async def test_constant_time_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    manager = GovernanceKeyManager(FakeRedis())
    path = await manager.initialize()
    key = path.read_text(encoding="utf-8")

    with patch("src.meta_mcp.governance.session_key.hmac.compare_digest", return_value=True) as mock_cmp:
        assert await manager.validate_and_rotate(key) is True
        assert mock_cmp.called


@pytest.mark.asyncio
async def test_key_hash_stored_in_redis_not_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    path = await manager.initialize()
    key = path.read_text(encoding="utf-8")

    stored = await redis.get("governance:session_key_hash")
    assert stored == hashlib.sha256(key.encode("utf-8")).hexdigest()
    assert stored != key


@pytest.mark.asyncio
async def test_startup_generates_key(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    from src.meta_mcp import supervisor

    fake_redis = FakeRedis()
    monkeypatch.setattr(supervisor, "check_redis_health", AsyncMock(return_value=(True, "ok")))
    monkeypatch.setattr(supervisor.governance_state, "_get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(supervisor.governance_state, "get_mode", AsyncMock(return_value=ExecutionMode.PERMISSION))
    monkeypatch.setattr(supervisor, "run_all_validations", AsyncMock(return_value=None))
    provider = type("P", (), {"is_available": AsyncMock(return_value=True), "get_name": lambda self: "mock"})()
    monkeypatch.setattr(supervisor, "get_approval_provider", AsyncMock(return_value=provider))
    monkeypatch.setattr(supervisor, "get_artifact_generator", lambda: type("A", (), {"artifacts_root": tmp_path})())

    async with supervisor.lifespan(None):
        assert (tmp_path / "governance.key").exists()


@pytest.mark.asyncio
async def test_shutdown_cleans_key_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    from src.meta_mcp import supervisor

    fake_redis = FakeRedis()
    monkeypatch.setattr(supervisor, "check_redis_health", AsyncMock(return_value=(True, "ok")))
    monkeypatch.setattr(supervisor.governance_state, "_get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(supervisor.governance_state, "get_mode", AsyncMock(return_value=ExecutionMode.PERMISSION))
    monkeypatch.setattr(supervisor, "run_all_validations", AsyncMock(return_value=None))
    provider = type("P", (), {"is_available": AsyncMock(return_value=True), "get_name": lambda self: "mock"})()
    monkeypatch.setattr(supervisor, "get_approval_provider", AsyncMock(return_value=provider))
    monkeypatch.setattr(supervisor, "get_artifact_generator", lambda: type("A", (), {"artifacts_root": tmp_path})())

    async with supervisor.lifespan(None):
        pass

    assert not (tmp_path / "governance.key").exists()


@pytest.mark.asyncio
async def test_invalid_key_attempt_is_audited(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    with patch("src.meta_mcp.state.audit_logger.log") as mock_log:
        with pytest.raises(PermissionError):
            await state.set_mode(ExecutionMode.BYPASS, session_key="bad")
    assert any(call.kwargs.get("key_valid") is False for call in mock_log.mock_calls)


@pytest.mark.asyncio
async def test_successful_mode_change_is_audited(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "GOVERNANCE_KEY_DIR", str(tmp_path))
    state = GovernanceState()
    redis = FakeRedis()
    manager = GovernanceKeyManager(redis)
    path = await manager.initialize()
    state.set_key_manager(manager)
    state.enable_mode_changes()
    state._get_redis = AsyncMock(return_value=redis)

    with patch("src.meta_mcp.state.audit_logger.log") as mock_log:
        await state.set_mode(
            ExecutionMode.BYPASS,
            session_key=path.read_text(encoding="utf-8"),
        )
    assert any(call.kwargs.get("requested_mode") == "bypass" for call in mock_log.mock_calls)


@pytest.mark.asyncio
async def test_default_governance_mode_only_cold_start(monkeypatch):
    monkeypatch.setattr(Config, "DEFAULT_EXECUTION_MODE", "read_only")
    state = GovernanceState()
    redis = FakeRedis()
    state._get_redis = AsyncMock(return_value=redis)

    first = await state.get_mode()
    assert first == ExecutionMode.READ_ONLY

    await redis.set("governance:mode", "permission")
    monkeypatch.setattr(Config, "DEFAULT_EXECUTION_MODE", "bypass")

    second = await state.get_mode()
    assert second == ExecutionMode.PERMISSION
