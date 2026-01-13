"""Filesystem and command tools as a standalone FastMCP server."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from loguru import logger

from src.meta_mcp.config import Config

# Create FastMCP server instance
core_server = FastMCP("CoreTools")


def _validate_path(path: str) -> Path:
    """
    Validate path is within WORKSPACE_ROOT (prevents traversal attacks).

    Args:
        path: Path to validate (can be relative or absolute)

    Returns:
        Resolved absolute Path object within workspace

    Raises:
        ToolError: If path is outside WORKSPACE_ROOT
    """
    workspace = Path(Config.WORKSPACE_ROOT).resolve()
    target = (workspace / path).resolve()

    # Check if target is within workspace using is_relative_to (Python 3.9+)
    # For compatibility, we use a try/except approach
    try:
        target.relative_to(workspace)
    except ValueError:
        raise ToolError(
            f"Path traversal detected: '{path}' resolves outside workspace '{workspace}'"
        )

    return target


@core_server.tool()
def read_file(path: str) -> str:
    """
    Read file contents from workspace.

    Args:
        path: Path to file (relative to workspace root)

    Returns:
        File contents as UTF-8 string
    """
    target = _validate_path(path)

    if not target.exists():
        raise ToolError(f"File not found: {path}")

    if not target.is_file():
        raise ToolError(f"Not a file: {path}")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ToolError(f"Failed to decode file as UTF-8: {e}")
    except Exception as e:
        raise ToolError(f"Failed to read file: {e}")


@core_server.tool()
def write_file(path: str, content: str) -> str:
    """
    Write content to file in workspace.

    Args:
        path: Path to file (relative to workspace root)
        content: Content to write (UTF-8)

    Returns:
        Success message with bytes written
    """
    target = _validate_path(path)

    # Create parent directories if they don't exist
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        bytes_written = target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {bytes_written} bytes to {path}"
    except Exception as e:
        raise ToolError(f"Failed to write file: {e}")


@core_server.tool()
def delete_file(path: str) -> str:
    """
    Delete file from workspace.

    Args:
        path: Path to file (relative to workspace root)

    Returns:
        Success message
    """
    target = _validate_path(path)

    if not target.exists():
        raise ToolError(f"File not found: {path}")

    if not target.is_file():
        raise ToolError(f"Not a file: {path}")

    try:
        target.unlink()
        return f"Successfully deleted file: {path}"
    except Exception as e:
        raise ToolError(f"Failed to delete file: {e}")


@core_server.tool()
def list_directory(path: str = ".") -> str:
    """
    List directory contents with type indicators.

    Args:
        path: Path to directory (relative to workspace root, default: ".")

    Returns:
        Formatted directory listing
    """
    target = _validate_path(path)

    if not target.exists():
        raise ToolError(f"Directory not found: {path}")

    if not target.is_dir():
        raise ToolError(f"Not a directory: {path}")

    try:
        entries = []
        for item in sorted(target.iterdir()):
            if item.is_dir():
                entries.append(f"[DIR]  {item.name}/")
            elif item.is_file():
                size = item.stat().st_size
                entries.append(f"[FILE] {item.name} ({size} bytes)")
            else:
                entries.append(f"[???]  {item.name}")

        if not entries:
            return f"Directory '{path}' is empty"

        return "\n".join(entries)
    except Exception as e:
        raise ToolError(f"Failed to list directory: {e}")


@core_server.tool()
def create_directory(path: str) -> str:
    """
    Create directory in workspace (including parent directories).

    Args:
        path: Path to directory (relative to workspace root)

    Returns:
        Success message
    """
    target = _validate_path(path)

    try:
        target.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        raise ToolError(f"Failed to create directory: {e}")


@core_server.tool()
def move_file(source: str, destination: str) -> str:
    """
    Move or rename file/directory within workspace.

    Args:
        source: Source path (relative to workspace root)
        destination: Destination path (relative to workspace root)

    Returns:
        Success message
    """
    source_path = _validate_path(source)
    dest_path = _validate_path(destination)

    if not source_path.exists():
        raise ToolError(f"Source not found: {source}")

    try:
        shutil.move(str(source_path), str(dest_path))
        return f"Successfully moved '{source}' to '{destination}'"
    except Exception as e:
        raise ToolError(f"Failed to move file: {e}")


@core_server.tool()
def remove_directory(path: str) -> str:
    """
    Remove directory from workspace.

    WARNING: Recursively deletes directory and all contents!

    Args:
        path: Path to directory (relative to workspace root)

    Returns:
        Success message
    """
    target = _validate_path(path)

    if not target.exists():
        raise ToolError(f"Directory not found: {path}")

    if not target.is_dir():
        raise ToolError(f"Not a directory: {path}")

    try:
        shutil.rmtree(str(target))
        return f"Successfully removed directory: {path}"
    except Exception as e:
        raise ToolError(f"Failed to remove directory: {e}")


@core_server.tool()
def execute_command(command: str, cwd: Optional[str] = None) -> str:
    """
    Execute shell command with timeout.

    Args:
        command: Shell command to execute
        cwd: Working directory (relative to workspace root, default: workspace root)

    Returns:
        Command output (stdout + stderr)
    """
    # Validate and resolve working directory
    if cwd is None:
        work_dir = Path(Config.WORKSPACE_ROOT).resolve()
    else:
        work_dir = _validate_path(cwd)
        if not work_dir.is_dir():
            raise ToolError(f"Working directory is not a directory: {cwd}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=Config.COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = []
        if result.stdout:
            output.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output.append(f"Exit code: {result.returncode}")

        return "\n\n".join(output) if output else "Command produced no output"

    except subprocess.TimeoutExpired:
        raise ToolError(
            f"Command timed out after {Config.COMMAND_TIMEOUT} seconds: {command}"
        )
    except Exception as e:
        raise ToolError(f"Failed to execute command: {e}")


@core_server.tool()
async def git_commit(message: str, cwd: Optional[str] = None) -> str:
    """
    Commit staged changes to git repository.

    Args:
        message: Commit message
        cwd: Working directory (defaults to WORKSPACE_ROOT)

    Returns:
        Commit output (SHA, summary)

    Raises:
        ToolError: If git commit fails or path validation fails

    Example:
        git_commit("Add new feature", "/workspace/myproject")
    """
    # Validate and resolve working directory
    if cwd is None:
        work_dir = Path(Config.WORKSPACE_ROOT).resolve()
    else:
        work_dir = _validate_path(cwd)
        if not work_dir.is_dir():
            raise ToolError(f"Working directory is not a directory: {cwd}")

    # Execute git commit
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=Config.COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

        if result.returncode != 0:
            raise ToolError(f"Git commit failed: {result.stderr}")

        logger.info(f"Git commit successful in {work_dir}")
        return json.dumps(output, indent=2)

    except subprocess.TimeoutExpired:
        raise ToolError(f"Git commit timed out after {Config.COMMAND_TIMEOUT}s")
    except Exception as e:
        raise ToolError(f"Git commit error: {e}")


@core_server.tool()
async def git_push(
    remote: str = "origin", branch: Optional[str] = None, cwd: Optional[str] = None
) -> str:
    """
    Push commits to remote git repository.

    Args:
        remote: Remote name (default: "origin")
        branch: Branch name (default: current branch)
        cwd: Working directory (defaults to WORKSPACE_ROOT)

    Returns:
        Push output

    Raises:
        ToolError: If git push fails or path validation fails

    Example:
        git_push("origin", "main", "/workspace/myproject")
    """
    # Validate and resolve working directory
    if cwd is None:
        work_dir = Path(Config.WORKSPACE_ROOT).resolve()
    else:
        work_dir = _validate_path(cwd)
        if not work_dir.is_dir():
            raise ToolError(f"Working directory is not a directory: {cwd}")

    # Build git push command
    cmd = ["git", "push", remote]
    if branch:
        cmd.append(branch)

    # Execute git push
    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=Config.COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

        if result.returncode != 0:
            raise ToolError(f"Git push failed: {result.stderr}")

        logger.info(f"Git push successful in {work_dir}")
        return json.dumps(output, indent=2)

    except subprocess.TimeoutExpired:
        raise ToolError(f"Git push timed out after {Config.COMMAND_TIMEOUT}s")
    except Exception as e:
        raise ToolError(f"Git push error: {e}")


@core_server.tool()
async def git_reset(
    ref: str = "HEAD", hard: bool = False, cwd: Optional[str] = None
) -> str:
    """
    Reset git repository to a specific commit.

    WARNING: --hard flag will discard all uncommitted changes!

    Args:
        ref: Git reference (commit SHA, branch, tag, default: "HEAD")
        hard: If True, discard all changes (--hard reset)
        cwd: Working directory (defaults to WORKSPACE_ROOT)

    Returns:
        Reset output

    Raises:
        ToolError: If git reset fails or path validation fails

    Example:
        git_reset("HEAD~1", hard=True, "/workspace/myproject")
    """
    # Validate and resolve working directory
    if cwd is None:
        work_dir = Path(Config.WORKSPACE_ROOT).resolve()
    else:
        work_dir = _validate_path(cwd)
        if not work_dir.is_dir():
            raise ToolError(f"Working directory is not a directory: {cwd}")

    # Build git reset command
    cmd = ["git", "reset"]
    if hard:
        cmd.append("--hard")
    cmd.append(ref)

    # Execute git reset
    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=Config.COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

        if result.returncode != 0:
            raise ToolError(f"Git reset failed: {result.stderr}")

        reset_type = "--hard" if hard else "--soft"
        logger.warning(f"Git reset {reset_type} to {ref} in {work_dir}")
        return json.dumps(output, indent=2)

    except subprocess.TimeoutExpired:
        raise ToolError(f"Git reset timed out after {Config.COMMAND_TIMEOUT}s")
    except Exception as e:
        raise ToolError(f"Git reset error: {e}")


# Export server for mounting
__all__ = ["core_server"]
