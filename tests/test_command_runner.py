import sys
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError

from meta_mcp.commands import CommandRunner


def test_command_runner_rejects_disallowed_command(tmp_path: Path) -> None:
    runner = CommandRunner(allowlist={"echo"})

    with pytest.raises(ToolError, match="allowlist"):
        runner.run("ls", cwd=tmp_path)


def test_command_runner_times_out(tmp_path: Path) -> None:
    runner = CommandRunner(
        allowlist={Path(sys.executable).name},
        timeout_seconds=0.01,
    )

    with pytest.raises(ToolError, match="timed out"):
        runner.run(f"{sys.executable} -c \"import time; time.sleep(1)\"", cwd=tmp_path)


def test_command_runner_success(tmp_path: Path) -> None:
    runner = CommandRunner(allowlist={Path(sys.executable).name})

    result = runner.run(f"{sys.executable} -c \"print('hello')\"", cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "hello"
