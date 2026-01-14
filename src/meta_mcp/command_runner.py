"""Command execution with allow/deny policy enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable, Optional

from loguru import logger


@dataclass(frozen=True)
class CommandPolicyDecision:
    """Result of command policy evaluation."""

    allowed: bool
    reason: str
    matched_pattern: Optional[str] = None


@dataclass(frozen=True)
class CommandResult:
    """Normalized command execution result."""

    command: str
    cwd: str
    allowed: bool
    policy_reason: str
    matched_pattern: Optional[str]
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "allowed": self.allowed,
            "policy_reason": self.policy_reason,
            "matched_pattern": self.matched_pattern,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


def _match_pattern(command: str, patterns: Iterable[str]) -> Optional[str]:
    for pattern in patterns:
        if re.search(pattern, command):
            return pattern
    return None


def evaluate_command_policy(
    command: str, allow_patterns: Iterable[str], deny_patterns: Iterable[str]
) -> CommandPolicyDecision:
    """Evaluate command against allow/deny patterns."""
    deny_match = _match_pattern(command, deny_patterns)
    if deny_match:
        return CommandPolicyDecision(
            allowed=False,
            reason="Command denied by policy.",
            matched_pattern=deny_match,
        )

    allow_patterns_list = list(allow_patterns)
    if allow_patterns_list:
        allow_match = _match_pattern(command, allow_patterns_list)
        if allow_match:
            return CommandPolicyDecision(
                allowed=True,
                reason="Command allowed by policy.",
                matched_pattern=allow_match,
            )
        return CommandPolicyDecision(
            allowed=False,
            reason="Command not in allow list.",
            matched_pattern=None,
        )

    return CommandPolicyDecision(
        allowed=True,
        reason="Command allowed (no allow list configured).",
        matched_pattern=None,
    )


def run_command(
    command: str,
    cwd: Path,
    timeout: int,
    allow_patterns: Iterable[str],
    deny_patterns: Iterable[str],
) -> CommandResult:
    """Execute a command with policy enforcement and normalized output."""
    policy = evaluate_command_policy(command, allow_patterns, deny_patterns)
    logger.info(
        "Command policy decision | allowed={} reason={} matched_pattern={} command={}",
        policy.allowed,
        policy.reason,
        policy.matched_pattern,
        command,
    )

    if not policy.allowed:
        return CommandResult(
            command=command,
            cwd=str(cwd),
            allowed=False,
            policy_reason=policy.reason,
            matched_pattern=policy.matched_pattern,
            stdout="",
            stderr="",
            exit_code=None,
            timed_out=False,
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return CommandResult(
            command=command,
            cwd=str(cwd),
            allowed=True,
            policy_reason=policy.reason,
            matched_pattern=policy.matched_pattern,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning(
            "Command timed out after {}s | command={}",
            timeout,
            command,
        )
        return CommandResult(
            command=command,
            cwd=str(cwd),
            allowed=True,
            policy_reason=policy.reason,
            matched_pattern=policy.matched_pattern,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            exit_code=None,
            timed_out=True,
        )
