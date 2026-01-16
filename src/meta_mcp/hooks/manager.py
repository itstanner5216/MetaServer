"""Hook manager for agent runtime spine."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from loguru import logger

from .gates import DEFAULT_GATES, Gate
from .models import (
    AgentBinding,
    AgentRunContext,
    HookStage,
    PolicyViolation,
    ToolReceipt,
)


class HookManager:
    """
    Central orchestrator for agent hook system.

    Features:
    - YAML-driven agent↔model bindings
    - Staged hook execution (before_tool_call, after_tool_result, on_error)
    - Pluggable gate system for policy enforcement
    - Trace/receipt generation for tool calls
    - Fail-safe: disabled when agent config is missing/empty

    Design principles:
    - Opt-in only: hooks run ONLY when agent binding is configured
    - Zero regression: existing paths unchanged when hooks disabled
    - Lease-integrated: respects existing lease/permission flow
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize hook manager.

        Args:
            config_path: Path to agents.yaml. If None, uses default location.
        """
        self._config_path = config_path or self._get_default_config_path()
        self._bindings: dict[str, AgentBinding] = {}
        self._active_contexts: dict[str, AgentRunContext] = {}
        self._gates: list[Gate] = list(DEFAULT_GATES)
        self._custom_hooks: dict[HookStage, list[Callable]] = {
            HookStage.BEFORE_TOOL_CALL: [],
            HookStage.AFTER_TOOL_RESULT: [],
            HookStage.ON_ERROR: [],
        }
        self._enabled = False
        self._loaded = False

        # Try to load config at init
        self._load_config()

    @staticmethod
    def _get_default_config_path() -> str:
        """Get default path to agents.yaml config."""
        # Check env var first
        env_path = os.getenv("AGENTS_YAML_PATH")
        if env_path:
            return env_path

        # Default: config/agents.yaml relative to project root
        return str(Path(__file__).parent.parent.parent.parent / "config" / "agents.yaml")

    def _load_config(self) -> bool:
        """
        Load agent bindings from YAML config.

        Returns:
            True if config loaded and has bindings, False otherwise
        """
        self._bindings.clear()
        self._enabled = False
        self._loaded = True

        config_path = Path(self._config_path)

        # If config doesn't exist, hooks are disabled
        if not config_path.exists():
            logger.debug(f"Agent config not found at {self._config_path}, hooks disabled")
            return False

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)

            # Empty or disabled config = hooks disabled
            if not data:
                logger.debug("Agent config is empty, hooks disabled")
                return False

            # Check global enabled flag
            if not data.get("enabled", True):
                logger.info("Agent hooks globally disabled via config")
                return False

            # Load agent bindings
            agents = data.get("agents", [])
            if not agents:
                logger.debug("No agent bindings defined, hooks disabled")
                return False

            for agent_data in agents:
                try:
                    binding = AgentBinding(
                        agent_id=agent_data["agent_id"],
                        role_id=agent_data.get("role_id", agent_data["agent_id"]),
                        model_id=agent_data["model_id"],
                        allowed_tools=agent_data.get("allowed_tools", []),
                        denied_tools=agent_data.get("denied_tools", []),
                        allowed_paths=agent_data.get("allowed_paths", []),
                        denied_paths=agent_data.get("denied_paths", []),
                        max_tool_calls=agent_data.get("max_tool_calls", 100),
                        max_tool_calls_per_tool=agent_data.get("max_tool_calls_per_tool", {}),
                        enabled=agent_data.get("enabled", True),
                        metadata=agent_data.get("metadata", {}),
                    )
                    if binding.enabled:
                        self._bindings[binding.agent_id] = binding
                        logger.debug(f"Loaded agent binding: {binding.agent_id}")
                except KeyError as e:
                    logger.error(f"Invalid agent binding (missing {e}): {agent_data}")
                    continue

            self._enabled = len(self._bindings) > 0
            if self._enabled:
                logger.info(f"Hook manager enabled with {len(self._bindings)} agent bindings")
            else:
                logger.debug("No enabled agent bindings, hooks disabled")

            return self._enabled

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse agent config: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load agent config: {e}")
            return False

    def reload_config(self) -> bool:
        """Reload config from disk."""
        return self._load_config()

    @property
    def enabled(self) -> bool:
        """Check if hook system is enabled."""
        return self._enabled

    def is_agent_mode(self, agent_id: Optional[str]) -> bool:
        """
        Check if request should use agent mode.

        Args:
            agent_id: Agent ID from request context

        Returns:
            True if agent_id is specified AND has a valid binding
        """
        if not self._enabled:
            return False
        if not agent_id:
            return False
        return agent_id in self._bindings

    def get_binding(self, agent_id: str) -> Optional[AgentBinding]:
        """Get agent binding by ID."""
        return self._bindings.get(agent_id)

    def start_agent_run(self, agent_id: str, session_id: str) -> Optional[AgentRunContext]:
        """
        Start a new agent run context.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier

        Returns:
            AgentRunContext if agent binding exists, None otherwise
        """
        binding = self.get_binding(agent_id)
        if not binding:
            logger.warning(f"No binding found for agent {agent_id}")
            return None

        ctx = AgentRunContext(
            agent_id=agent_id,
            session_id=session_id,
            binding=binding,
        )

        # Store by session for lookup during tool calls
        self._active_contexts[session_id] = ctx
        logger.info(f"Started agent run: agent={agent_id}, session={session_id}")
        return ctx

    def get_active_context(self, session_id: str) -> Optional[AgentRunContext]:
        """Get active agent context for session."""
        return self._active_contexts.get(session_id)

    def end_agent_run(self, session_id: str) -> Optional[AgentRunContext]:
        """
        End an agent run and return final context.

        Args:
            session_id: Session identifier

        Returns:
            Final AgentRunContext with all receipts, None if not found
        """
        ctx = self._active_contexts.pop(session_id, None)
        if ctx:
            ctx.active = False
            logger.info(
                f"Ended agent run: agent={ctx.agent_id}, session={session_id}, "
                f"tool_calls={ctx.tool_call_count}"
            )
        return ctx

    def add_gate(self, gate: Gate) -> None:
        """Add a custom gate to the pipeline."""
        self._gates.append(gate)

    def remove_gate(self, gate_type: str) -> bool:
        """Remove gates of a specific type."""
        original_len = len(self._gates)
        self._gates = [g for g in self._gates if g.gate_type.value != gate_type]
        return len(self._gates) < original_len

    def register_hook(self, stage: HookStage, hook: Callable) -> None:
        """Register a custom hook callback."""
        self._custom_hooks[stage].append(hook)

    def unregister_hook(self, stage: HookStage, hook: Callable) -> bool:
        """Unregister a custom hook callback."""
        try:
            self._custom_hooks[stage].remove(hook)
            return True
        except ValueError:
            return False

    async def run_before_tool_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[Optional[PolicyViolation], Optional[ToolReceipt]]:
        """
        Run before_tool_call hooks.

        Executes all gates and custom hooks before tool execution.

        Args:
            session_id: Session identifier
            tool_name: Name of tool being called
            arguments: Tool arguments

        Returns:
            Tuple of (violation if blocked, receipt for tracing)
            - If violation is not None, tool call should be blocked
            - Receipt should be passed to run_after_tool_result
        """
        ctx = self.get_active_context(session_id)
        if not ctx:
            # Not an agent run, skip hooks
            return None, None

        # Create receipt for tracing
        receipt = ToolReceipt(
            tool_name=tool_name,
            agent_id=ctx.agent_id,
            session_id=session_id,
            timestamp_start=datetime.now(timezone.utc),
            args_summary=self._summarize_args(arguments),
            hooks_applied=["before_tool_call"],
        )

        # Run gates
        for gate in self._gates:
            violation = gate.check(ctx, tool_name, arguments)
            if violation:
                receipt.finalize(success=False, error=str(violation))
                ctx.add_receipt(receipt)
                return violation, receipt

        # Run custom hooks
        for hook in self._custom_hooks[HookStage.BEFORE_TOOL_CALL]:
            try:
                result = hook(ctx, tool_name, arguments)
                if isinstance(result, PolicyViolation):
                    receipt.finalize(success=False, error=str(result))
                    ctx.add_receipt(receipt)
                    return result, receipt
            except Exception as e:
                logger.error(f"Custom before_tool_call hook failed: {e}")
                # Continue - don't block on hook errors

        # Increment budget counter BEFORE execution
        ctx.increment_tool_call(tool_name)

        return None, receipt

    async def run_after_tool_result(
        self,
        session_id: str,
        tool_name: str,
        result: Any,
        receipt: Optional[ToolReceipt],
        error: Optional[Exception] = None,
    ) -> None:
        """
        Run after_tool_result hooks.

        Finalizes receipt and runs post-execution hooks.

        Args:
            session_id: Session identifier
            tool_name: Name of tool that was called
            result: Tool execution result
            receipt: Receipt from before_tool_call
            error: Exception if tool failed
        """
        ctx = self.get_active_context(session_id)
        if not ctx:
            return

        # Finalize receipt
        if receipt:
            if error:
                receipt.finalize(
                    success=False,
                    error=str(error),
                )
                receipt.hooks_applied.append("after_tool_result:error")
            else:
                receipt.finalize(
                    success=True,
                    result_summary=self._summarize_result(result),
                )
                receipt.hooks_applied.append("after_tool_result:success")

            ctx.add_receipt(receipt)

        # Run custom hooks
        for hook in self._custom_hooks[HookStage.AFTER_TOOL_RESULT]:
            try:
                hook(ctx, tool_name, result, error)
            except Exception as e:
                logger.error(f"Custom after_tool_result hook failed: {e}")

    async def run_on_error(
        self,
        session_id: str,
        tool_name: str,
        error: Exception,
        receipt: Optional[ToolReceipt],
    ) -> None:
        """
        Run on_error hooks.

        Called when tool execution fails with an exception.

        Args:
            session_id: Session identifier
            tool_name: Name of tool that failed
            error: The exception that occurred
            receipt: Receipt from before_tool_call
        """
        ctx = self.get_active_context(session_id)
        if not ctx:
            return

        # Finalize receipt with error
        if receipt:
            receipt.finalize(success=False, error=str(error))
            receipt.hooks_applied.append("on_error")
            ctx.add_receipt(receipt)

        # Run custom hooks
        for hook in self._custom_hooks[HookStage.ON_ERROR]:
            try:
                hook(ctx, tool_name, error)
            except Exception as e:
                logger.error(f"Custom on_error hook failed: {e}")

    @staticmethod
    def _summarize_args(arguments: dict[str, Any], max_len: int = 200) -> dict[str, Any]:
        """Create a summary of arguments for logging."""
        summary = {}
        for key, value in arguments.items():
            str_val = str(value)
            if len(str_val) > max_len:
                summary[key] = str_val[:max_len] + "..."
            else:
                summary[key] = str_val
        return summary

    @staticmethod
    def _summarize_result(result: Any, max_len: int = 200) -> str:
        """Create a summary of result for logging."""
        str_result = str(result)
        if len(str_result) > max_len:
            return str_result[:max_len] + "..."
        return str_result


# Module-level singleton
hook_manager = HookManager()
