"""Approval provider system for governance elicitation.

Supports multiple approval mechanisms:
- DBus GUI (GNOME Shell extension)
- FastMCP ctx.elicit (client-side prompts)
- systemd-ask-password (terminal fallback)
"""

import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class ApprovalDecision(str, Enum):
    """User approval decision."""

    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ApprovalRequest:
    """Request for user approval of a tool operation.

    Attributes:
        request_id: Unique identifier for this approval request
        tool_name: Name of the tool requiring approval
        message: Human-readable description of the operation
        required_scopes: List of permission scopes required for this operation
        artifacts_path: Optional path to HTML/JSON artifacts for context
        timeout_seconds: How long to wait for user response
        context_metadata: Additional context (tool args, session info, etc.)
    """

    request_id: str
    tool_name: str
    message: str
    required_scopes: List[str]
    artifacts_path: Optional[str] = None
    timeout_seconds: int = 300
    context_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalResponse:
    """User response to approval request.

    Attributes:
        request_id: Matching request identifier
        decision: User's approval decision
        selected_scopes: Which scopes the user granted (subset of required_scopes)
        lease_seconds: How long the approval should last (0 = single-use)
        timestamp: When the decision was made
        error_message: Optional error message if decision was ERROR
    """

    request_id: str
    decision: ApprovalDecision
    selected_scopes: List[str] = field(default_factory=list)
    lease_seconds: int = 0
    timestamp: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def is_approved(self) -> bool:
        """Check if request was approved with at least one scope."""
        return self.decision == ApprovalDecision.APPROVED and len(self.selected_scopes) > 0


class ApprovalProvider(ABC):
    """Abstract base class for approval providers.

    Approval providers implement different mechanisms for obtaining
    user approval for sensitive operations. All methods are async
    to support network requests, GUI interactions, etc.
    """

    @abstractmethod
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Request user approval for a tool operation.

        Args:
            request: Approval request details

        Returns:
            User's approval response

        Raises:
            TimeoutError: If request times out
            Exception: On provider-specific errors
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this approval provider is available.

        Returns:
            True if provider can handle requests, False otherwise
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get human-readable name of this provider.

        Returns:
            Provider name (e.g., "DBus GUI", "FastMCP Elicit")
        """
        pass


class DBusGUIProvider(ApprovalProvider):
    """Approval provider using DBus to communicate with GNOME Shell extension.

    Requires:
    - GNOME Shell with custom extension installed
    - DBus session bus access
    - dasbus Python library
    """

    def __init__(self):
        """Initialize DBus GUI provider."""
        self._bus_name = "org.gnome.Shell.Extensions.MetaMCP"
        self._object_path = "/org/gnome/Shell/Extensions/MetaMCP"
        self._interface_name = "org.gnome.Shell.Extensions.MetaMCP"
        self._available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Check if DBus GUI is available.

        Returns:
            True if GNOME Shell extension is running
        """
        if self._available is not None:
            return self._available

        try:
            # Import dasbus only when needed (optional dependency)
            from dasbus.connection import SessionMessageBus

            bus = SessionMessageBus()
            proxy = bus.get_proxy(self._bus_name, self._object_path)

            # Test if proxy is accessible
            await asyncio.get_event_loop().run_in_executor(None, lambda: proxy.Introspect())
            self._available = True
            logger.info("DBus GUI approval provider is available")
            return True

        except ImportError:
            logger.warning("dasbus library not installed, DBus GUI unavailable")
            self._available = False
            return False
        except Exception as e:
            logger.debug(f"DBus GUI not available: {e}")
            self._available = False
            return False

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Request approval via GNOME Shell extension.

        Args:
            request: Approval request details

        Returns:
            User's approval response
        """
        try:
            from dasbus.connection import SessionMessageBus

            bus = SessionMessageBus()
            proxy = bus.get_proxy(self._bus_name, self._object_path)

            # Call DBus method with timeout
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: proxy.RequestApproval(
                        request.request_id,
                        request.tool_name,
                        request.message,
                        request.required_scopes,
                        request.artifacts_path or "",
                    ),
                ),
                timeout=request.timeout_seconds,
            )

            # Parse result (JSON string from extension)
            response_data = json.loads(result)

            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision(response_data.get("decision", "denied")),
                selected_scopes=response_data.get("selected_scopes", []),
                lease_seconds=response_data.get("lease_seconds", 0),
                timestamp=time.time(),
            )

        except asyncio.TimeoutError:
            logger.warning(f"Approval request {request.request_id} timed out")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.TIMEOUT,
                selected_scopes=[],
                error_message="User did not respond within timeout period",
            )
        except Exception as e:
            logger.error(f"DBus GUI approval failed: {e}")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.ERROR,
                selected_scopes=[],
                error_message=str(e),
            )

    def get_name(self) -> str:
        """Get provider name."""
        return "DBus GUI"


class FastMCPElicitProvider(ApprovalProvider):
    """Approval provider using FastMCP ctx.elicit() for client-side prompts.

    Requires:
    - FastMCP client that supports elicit() method
    - Context object passed from middleware
    """

    def __init__(self, context: Any = None):
        """Initialize FastMCP elicit provider.

        Args:
            context: FastMCP Context object (set later via set_context)
        """
        self._context = context

    def set_context(self, context: Any) -> None:
        """Set FastMCP context for elicitation.

        Args:
            context: FastMCP Context object from middleware
        """
        self._context = context

    async def is_available(self) -> bool:
        """Check if FastMCP elicit is available.

        Returns:
            True if context has elicit method
        """
        return (
            self._context is not None
            and hasattr(self._context, "elicit")
            and callable(self._context.elicit)
        )

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Request approval via FastMCP ctx.elicit().

        Args:
            request: Approval request details

        Returns:
            User's approval response
        """
        if not await self.is_available():
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.ERROR,
                selected_scopes=[],
                error_message="FastMCP context not available",
            )

        try:
            # Format elicitation message
            scope_list = "\n".join([f"  - {scope}" for scope in request.required_scopes])
            elicit_message = f"""
Tool: {request.tool_name}
Operation: {request.message}

Required Permissions:
{scope_list}

Respond with JSON or key=value pairs including decision, selected_scopes, lease_seconds.

JSON example:
{{"decision": "approved", "selected_scopes": [{", ".join([f'"{scope}"' for scope in request.required_scopes])}], "lease_seconds": 300}}

Key-value example (line or semicolon separated):
decision=approved
selected_scopes={", ".join(request.required_scopes)}
lease_seconds=300

Use lease_seconds=0 for single-use approval.
"""

            # Elicit approval from user
            response_payload = await asyncio.wait_for(
                self._context.elicit(elicit_message),
                timeout=request.timeout_seconds,
            )

            return self._parse_approval_payload(request, response_payload)

        except asyncio.TimeoutError:
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.TIMEOUT,
                selected_scopes=[],
                error_message="User did not respond within timeout period",
            )
        except Exception as e:
            logger.error(f"FastMCP elicit approval failed: {e}")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.ERROR,
                selected_scopes=[],
                error_message=str(e),
            )

    def get_name(self) -> str:
        """Get provider name."""
        return "FastMCP Elicit"

    @staticmethod
    def _parse_approval_payload(
        request: ApprovalRequest, response_payload: Any
    ) -> ApprovalResponse:
        payload = response_payload
        if hasattr(response_payload, "data"):
            payload = response_payload.data

        parsed = FastMCPElicitProvider._parse_structured_response(payload)
        if not parsed:
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.ERROR,
                selected_scopes=[],
                error_message="Invalid approval response format",
            )

        decision = FastMCPElicitProvider._parse_decision(parsed.get("decision"))
        selected_scopes = FastMCPElicitProvider._parse_scopes(parsed.get("selected_scopes"))
        lease_seconds = FastMCPElicitProvider._parse_lease_seconds(parsed.get("lease_seconds"))

        if decision is None:
            decision = (
                ApprovalDecision.APPROVED
                if selected_scopes
                else ApprovalDecision.DENIED
            )

        return ApprovalResponse(
            request_id=request.request_id,
            decision=decision,
            selected_scopes=selected_scopes,
            lease_seconds=lease_seconds,
            timestamp=time.time(),
        )

    @staticmethod
    def _parse_structured_response(payload: Any) -> Dict[str, Any]:
        if payload is None:
            return {}

        if isinstance(payload, dict):
            return {str(key).lower(): value for key, value in payload.items()}

        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return {}
            try:
                parsed_json = json.loads(stripped)
                if isinstance(parsed_json, dict):
                    return {
                        str(key).lower(): value for key, value in parsed_json.items()
                    }
            except json.JSONDecodeError:
                pass
            return FastMCPElicitProvider._parse_key_value_response(stripped)

        return {}

    @staticmethod
    def _parse_key_value_response(payload: str) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        for chunk in payload.split(";"):
            for line in chunk.splitlines():
                if not line.strip():
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                elif ":" in line:
                    key, value = line.split(":", 1)
                else:
                    continue
                parsed[key.strip().lower()] = value.strip()
        return parsed

    @staticmethod
    def _parse_decision(raw_value: Any) -> Optional[ApprovalDecision]:
        if raw_value is None:
            return None
        normalized = str(raw_value).strip().lower()
        if normalized in {"approved", "approve", "yes", "y"}:
            return ApprovalDecision.APPROVED
        if normalized in {"denied", "deny", "no", "n"}:
            return ApprovalDecision.DENIED
        if normalized == "timeout":
            return ApprovalDecision.TIMEOUT
        if normalized == "error":
            return ApprovalDecision.ERROR
        return None

    @staticmethod
    def _parse_scopes(raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [str(scope).strip() for scope in raw_value if str(scope).strip()]
        if isinstance(raw_value, str):
            stripped = raw_value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    parsed_json = json.loads(stripped)
                    if isinstance(parsed_json, list):
                        return [
                            str(scope).strip()
                            for scope in parsed_json
                            if str(scope).strip()
                        ]
                except json.JSONDecodeError:
                    pass
            return [scope.strip() for scope in stripped.split(",") if scope.strip()]
        return [str(raw_value).strip()] if str(raw_value).strip() else []

    @staticmethod
    def _parse_lease_seconds(raw_value: Any) -> int:
        if raw_value is None:
            return 0
        try:
            lease_seconds = int(float(raw_value))
        except (TypeError, ValueError):
            return 0
        return max(0, lease_seconds)


class SystemdFallbackProvider(ApprovalProvider):
    """Approval provider using systemd-ask-password for terminal prompts.

    Requires:
    - systemd-ask-password binary available
    - Terminal access (fallback for headless/SSH sessions)
    """

    async def is_available(self) -> bool:
        """Check if systemd-ask-password is available.

        Returns:
            True if systemd-ask-password binary exists
        """
        try:
            # Check if systemd-ask-password exists
            proc = await asyncio.create_subprocess_exec(
                "which",
                "systemd-ask-password",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Request approval via terminal prompt.

        Args:
            request: Approval request details

        Returns:
            User's approval response
        """
        try:
            # Format prompt message
            scope_list = ", ".join(request.required_scopes)
            prompt = f"Approve {request.tool_name}? ({request.message}) [Scopes: {scope_list}] (yes/no)"

            # Use systemd-ask-password
            proc = await asyncio.create_subprocess_exec(
                "systemd-ask-password",
                "--timeout",
                str(request.timeout_seconds),
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate()
            response_text = stdout.decode().strip().lower()

            if response_text in {"yes", "y"}:
                return ApprovalResponse(
                    request_id=request.request_id,
                    decision=ApprovalDecision.APPROVED,
                    selected_scopes=request.required_scopes,
                    lease_seconds=300,  # Default 5 minute lease
                    timestamp=time.time(),
                )
            else:
                return ApprovalResponse(
                    request_id=request.request_id,
                    decision=ApprovalDecision.DENIED,
                    selected_scopes=[],
                    timestamp=time.time(),
                )

        except Exception as e:
            logger.error(f"systemd fallback approval failed: {e}")
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.ERROR,
                selected_scopes=[],
                error_message=str(e),
            )

    def get_name(self) -> str:
        """Get provider name."""
        return "systemd Fallback"


class ApprovalProviderFactory:
    """Factory for creating and selecting approval providers.

    Handles provider selection based on configuration and availability.
    """

    @staticmethod
    async def create_provider(
        provider_name: Optional[str] = None, context: Any = None
    ) -> ApprovalProvider:
        """Create approval provider based on configuration.

        Args:
            provider_name: Explicit provider name or "auto" for auto-selection
            context: FastMCP context (for FastMCP elicit provider)

        Returns:
            First available approval provider

        Raises:
            RuntimeError: If no providers are available
        """
        # Get provider preference from env or param
        preference = provider_name or os.getenv("APPROVAL_PROVIDER", "auto")

        # Create provider instances
        providers = [
            DBusGUIProvider(),
            FastMCPElicitProvider(context),
            SystemdFallbackProvider(),
        ]

        # If explicit provider requested, try it first
        if preference != "auto":
            provider_map = {
                "dbus_gui": DBusGUIProvider,
                "fastmcp_elicit": FastMCPElicitProvider,
                "systemd_fallback": SystemdFallbackProvider,
            }

            if preference in provider_map:
                explicit_provider = provider_map[preference]()
                if isinstance(explicit_provider, FastMCPElicitProvider):
                    explicit_provider.set_context(context)

                if await explicit_provider.is_available():
                    logger.info(f"Using explicit approval provider: {explicit_provider.get_name()}")
                    return explicit_provider
                else:
                    logger.warning(
                        f"Requested provider {preference} not available, falling back to auto"
                    )

        # Auto-select first available provider
        for provider in providers:
            if await provider.is_available():
                logger.info(f"Auto-selected approval provider: {provider.get_name()}")
                return provider

        # No providers available - fail-safe by denying
        raise RuntimeError(
            "No approval providers available. Install dasbus for GUI support or ensure systemd is available."
        )


# Singleton instance
_approval_provider: Optional[ApprovalProvider] = None


async def get_approval_provider(context: Any = None) -> ApprovalProvider:
    """Get or create singleton approval provider instance.

    Args:
        context: FastMCP context (for FastMCP elicit provider)

    Returns:
        Configured approval provider

    Raises:
        RuntimeError: If no providers are available
    """
    global _approval_provider

    if _approval_provider is None:
        _approval_provider = await ApprovalProviderFactory.create_provider(context=context)

    # Update context if provider is FastMCP elicit
    if isinstance(_approval_provider, FastMCPElicitProvider) and context is not None:
        _approval_provider.set_context(context)

    return _approval_provider
