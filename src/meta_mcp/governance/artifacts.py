"""Artifact generation for approval requests.

Generates HTML and JSON artifacts to provide context for approval decisions.
All artifacts are stored under a safe root directory with path validation.
"""

import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class ArtifactGenerationError(Exception):
    """Raised when artifact generation fails."""

    pass


class ApprovalArtifactGenerator:
    """Generates approval context artifacts with security controls.

    Features:
    - HTML and JSON export formats
    - Safe root directory constraint
    - Path traversal prevention
    - File size limits
    - Automatic cleanup of old artifacts
    """

    def __init__(self, artifacts_root: str = "./artifacts/approvals"):
        """Initialize artifact generator.

        Args:
            artifacts_root: Root directory for artifacts (must be absolute or relative to workspace)
        """
        self.artifacts_root = Path(artifacts_root).resolve()
        self._ensure_safe_root()
        self._max_artifact_size = 10 * 1024 * 1024  # 10 MB
        self._max_artifacts = 100  # Limit total artifacts to prevent disk filling

    def _ensure_safe_root(self) -> None:
        """Ensure artifacts root directory exists and is safe.

        Creates directory if it doesn't exist, validates it's not a system directory.

        Raises:
            ArtifactGenerationError: If root directory is unsafe
        """
        # Prevent writing to system directories
        unsafe_roots = {
            Path("/"),
            Path("/etc"),
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/var"),
            Path("/sys"),
            Path("/proc"),
            Path("/dev"),
            Path("/boot"),
            Path("/root"),
        }

        for unsafe in unsafe_roots:
            try:
                if self.artifacts_root.resolve() == unsafe.resolve():
                    raise ArtifactGenerationError(
                        f"Artifacts root cannot be system directory: {unsafe}"
                    )
                if self.artifacts_root.resolve().is_relative_to(unsafe.resolve()):
                    if unsafe == Path("/var"):
                        # Allow /var/tmp and similar
                        if not self.artifacts_root.resolve().is_relative_to(Path("/var/tmp")):
                            if not self.artifacts_root.resolve().is_relative_to(Path("/var/log")):
                                raise ArtifactGenerationError(
                                    f"Artifacts root cannot be under {unsafe} (except /var/tmp, /var/log)"
                                )
                    else:
                        raise ArtifactGenerationError(
                            f"Artifacts root cannot be under system directory: {unsafe}"
                        )
            except ValueError:
                # is_relative_to raises ValueError if not relative, which is fine
                pass

        # Create directory if it doesn't exist
        try:
            self.artifacts_root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ArtifactGenerationError(
                f"Failed to create artifacts directory {self.artifacts_root}: {e}"
            )

        logger.info(f"Artifact generator initialized with root: {self.artifacts_root}")

    def _validate_path(self, artifact_path: str) -> Path:
        """Validate artifact path is within safe root.

        Args:
            artifact_path: Path to validate

        Returns:
            Resolved absolute path

        Raises:
            ArtifactGenerationError: If path is outside safe root
        """
        # Resolve path and ensure it's under artifacts_root
        resolved = (self.artifacts_root / artifact_path).resolve()

        if not resolved.is_relative_to(self.artifacts_root):
            raise ArtifactGenerationError(
                f"Path traversal detected: {artifact_path} resolves outside artifacts root"
            )

        return resolved

    def _cleanup_old_artifacts(self) -> None:
        """Remove old artifacts if count exceeds limit.

        Removes oldest artifacts first based on modification time.
        """
        try:
            artifacts = list(self.artifacts_root.glob("**/*"))
            artifacts = [f for f in artifacts if f.is_file()]

            if len(artifacts) > self._max_artifacts:
                # Sort by modification time (oldest first)
                artifacts.sort(key=lambda f: f.stat().st_mtime)

                # Remove oldest artifacts to get below limit
                to_remove = len(artifacts) - self._max_artifacts
                for artifact in artifacts[:to_remove]:
                    try:
                        artifact.unlink()
                        logger.debug(f"Removed old artifact: {artifact}")
                    except Exception as e:
                        logger.warning(f"Failed to remove old artifact {artifact}: {e}")

        except Exception as e:
            logger.warning(f"Failed to cleanup old artifacts: {e}")

    def generate_html_artifact(
        self,
        request_id: str,
        tool_name: str,
        message: str,
        required_scopes: List[str],
        arguments: Dict[str, Any],
        context_metadata: Dict[str, Any],
    ) -> str:
        """Generate HTML artifact for approval request.

        Args:
            request_id: Unique request identifier
            tool_name: Name of the tool
            message: Approval request message
            required_scopes: Required permission scopes
            arguments: Tool arguments
            context_metadata: Additional context

        Returns:
            Validated absolute path to generated HTML file

        Raises:
            ArtifactGenerationError: If generation fails
        """
        try:
            # Generate filename from request_id
            filename = f"{request_id}.html"
            artifact_path = self._validate_path(filename)

            # Generate HTML content
            html_content = self._generate_html_content(
                request_id=request_id,
                tool_name=tool_name,
                message=message,
                required_scopes=required_scopes,
                arguments=arguments,
                context_metadata=context_metadata,
            )

            # Check size limit
            if len(html_content.encode()) > self._max_artifact_size:
                raise ArtifactGenerationError(
                    f"HTML artifact exceeds size limit ({self._max_artifact_size} bytes)"
                )

            # Write file
            artifact_path.write_text(html_content, encoding="utf-8")
            logger.info(f"Generated HTML artifact: {artifact_path}")

            # Cleanup old artifacts
            self._cleanup_old_artifacts()

            return str(artifact_path)

        except ArtifactGenerationError:
            raise
        except Exception as e:
            raise ArtifactGenerationError(f"Failed to generate HTML artifact: {e}")

    def generate_json_artifact(
        self,
        request_id: str,
        tool_name: str,
        message: str,
        required_scopes: List[str],
        arguments: Dict[str, Any],
        context_metadata: Dict[str, Any],
    ) -> str:
        """Generate JSON artifact for approval request.

        Args:
            request_id: Unique request identifier
            tool_name: Name of the tool
            message: Approval request message
            required_scopes: Required permission scopes
            arguments: Tool arguments
            context_metadata: Additional context

        Returns:
            Validated absolute path to generated JSON file

        Raises:
            ArtifactGenerationError: If generation fails
        """
        try:
            # Generate filename from request_id
            filename = f"{request_id}.json"
            artifact_path = self._validate_path(filename)

            # Generate JSON content
            json_data = {
                "request_id": request_id,
                "tool_name": tool_name,
                "message": message,
                "required_scopes": required_scopes,
                "arguments": arguments,
                "context_metadata": context_metadata,
                "generated_at": datetime.utcnow().isoformat(),
            }

            json_content = json.dumps(json_data, indent=2, ensure_ascii=False)

            # Check size limit
            if len(json_content.encode()) > self._max_artifact_size:
                raise ArtifactGenerationError(
                    f"JSON artifact exceeds size limit ({self._max_artifact_size} bytes)"
                )

            # Write file
            artifact_path.write_text(json_content, encoding="utf-8")
            logger.info(f"Generated JSON artifact: {artifact_path}")

            # Cleanup old artifacts
            self._cleanup_old_artifacts()

            return str(artifact_path)

        except ArtifactGenerationError:
            raise
        except Exception as e:
            raise ArtifactGenerationError(f"Failed to generate JSON artifact: {e}")

    def _generate_html_content(
        self,
        request_id: str,
        tool_name: str,
        message: str,
        required_scopes: List[str],
        arguments: Dict[str, Any],
        context_metadata: Dict[str, Any],
    ) -> str:
        """Generate HTML content for approval artifact.

        Args:
            request_id: Request identifier
            tool_name: Tool name
            message: Approval message
            required_scopes: Required scopes
            arguments: Tool arguments
            context_metadata: Additional context

        Returns:
            HTML content as string
        """
        # Escape all user-provided content
        safe_request_id = html.escape(request_id)
        safe_tool_name = html.escape(tool_name)
        safe_message = html.escape(message)

        # Generate scopes list
        scopes_html = "\n".join(
            [f"        <li><code>{html.escape(scope)}</code></li>" for scope in required_scopes]
        )

        # Generate arguments table
        args_rows = []
        for key, value in arguments.items():
            safe_key = html.escape(str(key))
            safe_value = html.escape(str(value)[:200])  # Truncate long values
            args_rows.append(
                f"""
          <tr>
            <td><strong>{safe_key}</strong></td>
            <td><code>{safe_value}</code></td>
          </tr>"""
            )
        args_html = "\n".join(args_rows) if args_rows else "<tr><td colspan='2'><em>No arguments</em></td></tr>"

        # Generate metadata
        session_id = html.escape(str(context_metadata.get("session_id", "unknown")))
        context_key = html.escape(str(context_metadata.get("context_key", "unknown")))
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Approval Request: {safe_tool_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 900px;
            margin: 40px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            margin-top: 0;
            font-size: 24px;
        }}
        h2 {{
            color: #666;
            font-size: 18px;
            margin-top: 24px;
            margin-bottom: 12px;
        }}
        .metadata {{
            background: #f8f9fa;
            border-left: 4px solid #007bff;
            padding: 12px;
            margin: 16px 0;
            font-size: 14px;
        }}
        .metadata strong {{
            color: #495057;
        }}
        ul {{
            list-style: none;
            padding: 0;
        }}
        ul li {{
            padding: 8px;
            margin: 4px 0;
            background: #e9ecef;
            border-radius: 4px;
        }}
        code {{
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .message {{
            white-space: pre-wrap;
            background: #f8f9fa;
            padding: 16px;
            border-radius: 4px;
            margin: 12px 0;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Approval Request</h1>
        <div class="metadata">
            <strong>Request ID:</strong> <code>{safe_request_id}</code><br>
            <strong>Tool:</strong> <code>{safe_tool_name}</code><br>
            <strong>Session:</strong> <code>{session_id}</code><br>
            <strong>Context:</strong> <code>{context_key}</code><br>
            <strong>Generated:</strong> {timestamp}
        </div>
    </div>

    <div class="card">
        <h2>Message</h2>
        <div class="message">{safe_message}</div>
    </div>

    <div class="card">
        <h2>Required Permissions</h2>
        <ul>
{scopes_html}
        </ul>
    </div>

    <div class="card">
        <h2>Tool Arguments</h2>
        <table>
{args_html}
        </table>
    </div>
</body>
</html>"""

        return html_template


# Singleton instance
_artifact_generator: Optional[ApprovalArtifactGenerator] = None


def get_artifact_generator(artifacts_root: Optional[str] = None) -> ApprovalArtifactGenerator:
    """Get or create singleton artifact generator.

    Args:
        artifacts_root: Optional custom artifacts root directory

    Returns:
        ApprovalArtifactGenerator instance
    """
    global _artifact_generator

    if _artifact_generator is None:
        root = artifacts_root or os.getenv("ARTIFACTS_ROOT", "./artifacts/approvals")
        _artifact_generator = ApprovalArtifactGenerator(artifacts_root=root)

    return _artifact_generator
