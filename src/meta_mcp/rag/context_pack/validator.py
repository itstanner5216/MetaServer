# context_pack/validator.py
"""
Phase 5: ContextPack Validator for RAG System.

Validates ContextPack signatures and expiration.
Used by Generator to ensure context hasn't been tampered with.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from .builder import ContextPack

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Validation Result Types
# -----------------------------------------------------------------------------


class ValidationStatus(Enum):
    """Validation status codes."""
    VALID = "valid"
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED = "expired"
    MALFORMED = "malformed"


@dataclass
class ValidationResult:
    """
    Result of ContextPack validation.

    Attributes:
        is_valid: Whether the pack passed all validation checks
        status: Detailed validation status code
        error_message: Human-readable error message (empty if valid)
        validated_at: When validation was performed
    """
    is_valid: bool
    status: ValidationStatus
    error_message: str
    validated_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "status": self.status.value,
            "error_message": self.error_message,
            "validated_at": self.validated_at.isoformat(),
        }


# -----------------------------------------------------------------------------
# ContextPack Validator
# -----------------------------------------------------------------------------


class ContextPackValidator:
    """
    Validates ContextPack signatures and expiration.

    Used by Generator to ensure context hasn't been tampered with
    before using it for generation. Performs two main checks:

    1. Signature Verification: Recomputes HMAC-SHA256 signature
       from pack data and compares with stored signature.

    2. Expiration Check: Ensures current time is before expires_at.

    Example:
        validator = ContextPackValidator(hmac_secret="your-secret-key")

        result = validator.validate(pack)
        if result.is_valid:
            # Safe to use pack for generation
            pass
        else:
            # Pack is invalid or expired
            logger.error(f"Pack validation failed: {result.error_message}")
    """

    def __init__(self, hmac_secret: str):
        """
        Initialize the ContextPack validator.

        Args:
            hmac_secret: Secret key for HMAC-SHA256 verification
                        (must match the key used by ContextPackBuilder)

        Raises:
            ValueError: If hmac_secret is empty
        """
        if not hmac_secret:
            raise ValueError("hmac_secret cannot be empty")

        self._hmac_secret = hmac_secret

        # Metrics
        self._validations_performed = 0
        self._validations_passed = 0
        self._validations_failed_signature = 0
        self._validations_failed_expired = 0

        logger.info("ContextPackValidator initialized")

    def validate(self, pack: ContextPack) -> ValidationResult:
        """
        Validate a ContextPack's signature and expiration.

        Performs the following checks in order:
        1. Verifies HMAC-SHA256 signature matches pack data
        2. Checks that pack has not expired

        Args:
            pack: ContextPack to validate

        Returns:
            ValidationResult with validation status and any error message
        """
        self._validations_performed += 1
        validated_at = datetime.utcnow()

        logger.debug(f"Validating ContextPack: pack_id={pack.pack_id}")

        try:
            # Check 1: Verify signature
            if not self._verify_signature(pack):
                self._validations_failed_signature += 1
                logger.warning(
                    f"Signature verification failed: pack_id={pack.pack_id}"
                )
                return ValidationResult(
                    is_valid=False,
                    status=ValidationStatus.INVALID_SIGNATURE,
                    error_message="Signature verification failed - pack may have been tampered with",
                    validated_at=validated_at,
                )

            # Check 2: Check expiration
            if self.is_expired(pack):
                self._validations_failed_expired += 1
                logger.warning(
                    f"Pack expired: pack_id={pack.pack_id}, "
                    f"expires_at={pack.expires_at.isoformat()}"
                )
                return ValidationResult(
                    is_valid=False,
                    status=ValidationStatus.EXPIRED,
                    error_message=f"Pack expired at {pack.expires_at.isoformat()}",
                    validated_at=validated_at,
                )

            # All checks passed
            self._validations_passed += 1
            logger.debug(f"Pack validation passed: pack_id={pack.pack_id}")

            return ValidationResult(
                is_valid=True,
                status=ValidationStatus.VALID,
                error_message="",
                validated_at=validated_at,
            )

        except Exception as e:
            logger.error(f"Validation error: pack_id={pack.pack_id}, error={e}")
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.MALFORMED,
                error_message=f"Validation error: {str(e)}",
                validated_at=validated_at,
            )

    def _verify_signature(self, pack: ContextPack) -> bool:
        """
        Verify the HMAC-SHA256 signature of a ContextPack.

        Recomputes the signature from pack data (excluding the signature
        field itself) and compares with the stored signature using
        constant-time comparison to prevent timing attacks.

        Args:
            pack: ContextPack to verify

        Returns:
            True if signature is valid, False otherwise
        """
        # Rebuild pack data without signature (same structure as builder)
        pack_data = {
            "pack_id": pack.pack_id,
            "query": pack.query,
            "query_rewritten": pack.query_rewritten,
            "lease_id": pack.lease_id,
            "scope": pack.scope,
            "embedding_config": pack.embedding_config,
            "retrieval_config": pack.retrieval_config,
            "candidates_raw": pack.candidates_raw,
            "candidates_selected": pack.candidates_selected,
            "selected_chunk_full_text": pack.selected_chunk_full_text,
            "explainer_output": pack.explainer_output,
            "token_budget": pack.token_budget,
            "created_at": pack.created_at.isoformat(),
            "expires_at": pack.expires_at.isoformat(),
        }

        # Create canonical representation (same as builder)
        canonical = json.dumps(
            pack_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

        # Compute expected signature
        expected_signature = hmac.new(
            self._hmac_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, pack.signature)

    def is_expired(self, pack: ContextPack) -> bool:
        """
        Check if a ContextPack has expired.

        Args:
            pack: ContextPack to check

        Returns:
            True if current time is past expires_at, False otherwise
        """
        return datetime.utcnow() > pack.expires_at

    def time_until_expiration(self, pack: ContextPack) -> Optional[float]:
        """
        Get seconds until pack expiration.

        Args:
            pack: ContextPack to check

        Returns:
            Seconds until expiration, or None if already expired
        """
        remaining = (pack.expires_at - datetime.utcnow()).total_seconds()
        return remaining if remaining > 0 else None

    def get_metrics(self) -> dict:
        """
        Get validator metrics.

        Returns:
            Dict with validation statistics
        """
        return {
            "validations_performed": self._validations_performed,
            "validations_passed": self._validations_passed,
            "validations_failed_signature": self._validations_failed_signature,
            "validations_failed_expired": self._validations_failed_expired,
            "pass_rate": (
                self._validations_passed / self._validations_performed
                if self._validations_performed > 0
                else 0.0
            ),
        }


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def create_validator(hmac_secret: str) -> ContextPackValidator:
    """
    Create a ContextPackValidator with the given secret.

    Args:
        hmac_secret: Secret key for HMAC-SHA256 verification

    Returns:
        Configured ContextPackValidator instance
    """
    return ContextPackValidator(hmac_secret=hmac_secret)


def validate_pack(pack: ContextPack, hmac_secret: str) -> Tuple[bool, str]:
    """
    Convenience function to validate a pack with a given secret.

    Args:
        pack: ContextPack to validate
        hmac_secret: Secret key for verification

    Returns:
        Tuple of (is_valid, error_message)
    """
    validator = ContextPackValidator(hmac_secret=hmac_secret)
    result = validator.validate(pack)
    return result.is_valid, result.error_message
