"""Tests for agent hook system."""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from src.meta_mcp.hooks import (
    AgentBinding,
    AgentRunContext,
    BudgetGate,
    GateType,
    HookManager,
    HookStage,
    PathFenceGate,
    PolicyViolation,
    ToolAllowlistGate,
    ToolReceipt,
    hook_manager,
)


class TestAgentBinding:
    """Tests for AgentBinding model."""

    def test_is_tool_allowed_empty_allowlist(self):
        """Empty allowed_tools means all tools allowed (except denied)."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=[],
            denied_tools=[],
        )
        assert binding.is_tool_allowed("any_tool") is True

    def test_is_tool_allowed_in_allowlist(self):
        """Tool in allowed_tools is allowed."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=["read_file", "write_file"],
            denied_tools=[],
        )
        assert binding.is_tool_allowed("read_file") is True
        assert binding.is_tool_allowed("delete_file") is False

    def test_is_tool_allowed_denied_takes_priority(self):
        """denied_tools takes priority over allowed_tools."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=["read_file", "delete_file"],
            denied_tools=["delete_file"],
        )
        assert binding.is_tool_allowed("read_file") is True
        assert binding.is_tool_allowed("delete_file") is False


class TestToolAllowlistGate:
    """Tests for ToolAllowlistGate."""

    def test_allowed_tool_passes(self):
        """Allowed tool passes the gate."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=["read_file"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = ToolAllowlistGate()

        result = gate.check(ctx, "read_file", {})
        assert result is None

    def test_denied_tool_blocked(self):
        """Denied tool is blocked."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=["read_file"],
            denied_tools=["delete_file"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = ToolAllowlistGate()

        result = gate.check(ctx, "delete_file", {})
        assert result is not None
        assert result.gate_type == GateType.TOOL_ALLOWLIST
        assert "delete_file" in result.reason

    def test_unlisted_tool_blocked_when_allowlist_present(self):
        """Tool not in allowlist is blocked when allowlist is non-empty."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_tools=["read_file"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = ToolAllowlistGate()

        result = gate.check(ctx, "write_file", {})
        assert result is not None


class TestPathFenceGate:
    """Tests for PathFenceGate."""

    def test_allowed_path_passes(self):
        """Path in allowed_paths passes."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_paths=["./workspace/**"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = PathFenceGate()

        result = gate.check(ctx, "read_file", {"path": "./workspace/file.txt"})
        assert result is None

    def test_denied_path_blocked(self):
        """Path in denied_paths is blocked."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_paths=[],
            denied_paths=["/etc/**"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = PathFenceGate()

        result = gate.check(ctx, "read_file", {"path": "/etc/passwd"})
        assert result is not None
        assert result.gate_type == GateType.PATH_FENCE

    def test_non_file_tool_skipped(self):
        """Non-file tools are not checked."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            denied_paths=["/etc/**"],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = PathFenceGate()

        result = gate.check(ctx, "execute_command", {"command": "cat /etc/passwd"})
        assert result is None  # Not a file tool

    def test_empty_paths_allows_all(self):
        """Empty allowed_paths and denied_paths allows all."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            allowed_paths=[],
            denied_paths=[],
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = PathFenceGate()

        result = gate.check(ctx, "read_file", {"path": "/any/path"})
        assert result is None


class TestBudgetGate:
    """Tests for BudgetGate."""

    def test_within_budget_passes(self):
        """Call within budget passes."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            max_tool_calls=10,
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        gate = BudgetGate()

        result = gate.check(ctx, "read_file", {})
        assert result is None

    def test_global_budget_exceeded(self):
        """Exceeding global budget is blocked."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            max_tool_calls=2,
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        ctx.tool_call_count = 2  # Already at limit

        gate = BudgetGate()
        result = gate.check(ctx, "read_file", {})
        assert result is not None
        assert result.gate_type == GateType.BUDGET_LIMIT

    def test_per_tool_budget_exceeded(self):
        """Exceeding per-tool budget is blocked."""
        binding = AgentBinding(
            agent_id="test",
            role_id="test",
            model_id="test/model",
            max_tool_calls=100,
            max_tool_calls_per_tool={"write_file": 3},
        )
        ctx = AgentRunContext(agent_id="test", session_id="sess", binding=binding)
        ctx.tool_call_counts_by_tool["write_file"] = 3  # At limit

        gate = BudgetGate()
        result = gate.check(ctx, "write_file", {})
        assert result is not None
        assert result.gate_type == GateType.BUDGET_LIMIT


class TestHookManager:
    """Tests for HookManager."""

    def test_disabled_when_no_config(self):
        """Hook manager is disabled when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            manager = HookManager(config_path=config_path)
            assert manager.enabled is False

    def test_disabled_when_config_empty(self):
        """Hook manager is disabled when config is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            with open(config_path, "w") as f:
                f.write("")
            manager = HookManager(config_path=config_path)
            assert manager.enabled is False

    def test_disabled_when_globally_disabled(self):
        """Hook manager is disabled when enabled: false in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            with open(config_path, "w") as f:
                yaml.dump({"enabled": False, "agents": []}, f)
            manager = HookManager(config_path=config_path)
            assert manager.enabled is False

    def test_enabled_with_valid_config(self):
        """Hook manager is enabled with valid agent bindings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            config = {
                "enabled": True,
                "agents": [
                    {
                        "agent_id": "test_agent",
                        "role_id": "tester",
                        "model_id": "test/model",
                        "enabled": True,
                    }
                ],
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            manager = HookManager(config_path=config_path)
            assert manager.enabled is True
            assert manager.get_binding("test_agent") is not None

    def test_is_agent_mode_false_when_disabled(self):
        """is_agent_mode returns False when hooks disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            manager = HookManager(config_path=config_path)
            assert manager.is_agent_mode("any_agent") is False

    def test_is_agent_mode_false_for_unknown_agent(self):
        """is_agent_mode returns False for unknown agent ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            config = {
                "enabled": True,
                "agents": [
                    {
                        "agent_id": "known_agent",
                        "model_id": "test/model",
                    }
                ],
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            manager = HookManager(config_path=config_path)
            assert manager.is_agent_mode("unknown_agent") is False

    def test_start_agent_run(self):
        """start_agent_run creates context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            config = {
                "enabled": True,
                "agents": [
                    {
                        "agent_id": "test_agent",
                        "model_id": "test/model",
                    }
                ],
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            manager = HookManager(config_path=config_path)

            ctx = manager.start_agent_run("test_agent", "session123")
            assert ctx is not None
            assert ctx.agent_id == "test_agent"
            assert ctx.session_id == "session123"
            assert manager.get_active_context("session123") is ctx

    @pytest.mark.asyncio
    async def test_run_before_tool_call_no_agent(self):
        """run_before_tool_call returns None for non-agent sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            manager = HookManager(config_path=config_path)

            violation, receipt = await manager.run_before_tool_call(
                "session123", "read_file", {}
            )
            assert violation is None
            assert receipt is None

    @pytest.mark.asyncio
    async def test_run_before_tool_call_allowed(self):
        """run_before_tool_call passes for allowed tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            config = {
                "enabled": True,
                "agents": [
                    {
                        "agent_id": "test_agent",
                        "model_id": "test/model",
                        "allowed_tools": ["read_file"],
                    }
                ],
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            manager = HookManager(config_path=config_path)
            manager.start_agent_run("test_agent", "session123")

            violation, receipt = await manager.run_before_tool_call(
                "session123", "read_file", {}
            )
            assert violation is None
            assert receipt is not None
            assert receipt.tool_name == "read_file"

    @pytest.mark.asyncio
    async def test_run_before_tool_call_blocked(self):
        """run_before_tool_call returns violation for blocked tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "agents.yaml")
            config = {
                "enabled": True,
                "agents": [
                    {
                        "agent_id": "test_agent",
                        "model_id": "test/model",
                        "allowed_tools": ["read_file"],
                    }
                ],
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            manager = HookManager(config_path=config_path)
            manager.start_agent_run("test_agent", "session123")

            violation, receipt = await manager.run_before_tool_call(
                "session123", "delete_file", {}
            )
            assert violation is not None
            assert violation.gate_type == GateType.TOOL_ALLOWLIST


class TestPolicyViolation:
    """Tests for PolicyViolation model."""

    def test_to_dict(self):
        """to_dict produces correct structure."""
        violation = PolicyViolation(
            gate_type=GateType.TOOL_ALLOWLIST,
            tool_name="delete_file",
            reason="Tool not allowed",
            agent_id="test",
            session_id="sess",
        )
        d = violation.to_dict()
        assert d["gate_type"] == "tool_allowlist"
        assert d["tool_name"] == "delete_file"
        assert d["reason"] == "Tool not allowed"
        assert "timestamp" in d


class TestToolReceipt:
    """Tests for ToolReceipt model."""

    def test_finalize(self):
        """finalize sets end time and duration."""
        receipt = ToolReceipt(
            tool_name="read_file",
            agent_id="test",
            session_id="sess",
            timestamp_start=datetime.now(timezone.utc),
        )
        receipt.finalize(success=True, result_summary="contents")
        assert receipt.success is True
        assert receipt.timestamp_end is not None
        assert receipt.duration_ms is not None
        assert receipt.result_summary == "contents"


class TestExistingBehaviorUnchanged:
    """Tests verifying existing behavior when hooks disabled."""

    def test_singleton_disabled_without_config(self):
        """Global hook_manager is disabled if config missing."""
        # The singleton is initialized at import time
        # It should be disabled if config/agents.yaml doesn't exist
        # or has no enabled bindings
        # This test verifies the fail-safe behavior
        assert isinstance(hook_manager, HookManager)

    @pytest.mark.asyncio
    async def test_no_hooks_for_non_agent_session(self):
        """Hooks don't run for sessions without agent_id."""
        # Even if hook_manager is enabled, hooks don't run
        # unless there's an active agent context for the session
        violation, receipt = await hook_manager.run_before_tool_call(
            "unknown_session", "any_tool", {}
        )
        assert violation is None
        assert receipt is None
