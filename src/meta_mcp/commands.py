"""Command execution utilities with safety checks."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

from fastmcp.exceptions import ToolError

from .config import Config


class CommandRunner:
    """Execute commands with validation and timeout enforcement."""

    def __init__(
        self,
        *,
        allowlist: Iterable[str] | None = None,
        denylist: Iterable[str] | None = None,
        timeout_seconds: int | None = None,
        restrictions_relaxed: bool | None = None,
    ) -> None:
        self._allowlist = {item.lower() for item in (allowlist or Config.COMMAND_ALLOWLIST)}
        self._denylist = {item.lower() for item in (denylist or Config.COMMAND_DENYLIST)}
        self._timeout_seconds = timeout_seconds or Config.COMMAND_TIMEOUT
        self._restrictions_relaxed = (
            Config.COMMAND_RESTRICTIONS_RELAXED
            if restrictions_relaxed is None
            else restrictions_relaxed
        )

    def run(self, command: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
        args = self._parse_command(command)
        self._validate_command(args)

        try:
            return subprocess.run(
                args,
                shell=False,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"Command timed out after {self._timeout_seconds} seconds: {command}"
            ) from exc
        except FileNotFoundError as exc:
            raise ToolError(f"Command not found: {args[0]}") from exc
        except Exception as exc:
            raise ToolError(f"Failed to execute command: {exc}") from exc

    def _parse_command(self, command: str) -> Sequence[str]:
        if not command or not command.strip():
            raise ToolError("Command cannot be empty")
        try:
            args = shlex.split(command)
        except ValueError as exc:
            raise ToolError(f"Invalid command syntax: {exc}") from exc
        if not args:
            raise ToolError("Command cannot be empty")
        return args

    def _validate_command(self, args: Sequence[str]) -> None:
        if self._restrictions_relaxed:
            return

        command_name = Path(args[0]).name.lower()

        if self._denylist and command_name in self._denylist:
            raise ToolError(f"Command '{command_name}' is denied")

        if self._allowlist and command_name not in self._allowlist:
            raise ToolError(f"Command '{command_name}' is not in the allowlist")


def format_command_output(result: subprocess.CompletedProcess[str]) -> str:
    """Format command output for compatibility with existing tooling."""
    output_parts = []
    if result.stdout:
        output_parts.append(f"STDOUT:\n{result.stdout}")
    if result.stderr:
        output_parts.append(f"STDERR:\n{result.stderr}")
    output_parts.append(f"Exit code: {result.returncode}")
    return "\n\n".join(output_parts) if output_parts else "Command produced no output"
