"""Centralized configuration for MetaMCP."""

import os


class Config:
    """
    MetaMCP configuration with environment variable overrides.

    All configuration values are centralized here with sensible defaults.
    Values can be overridden via environment variables.
    """

    @staticmethod
    def _parse_port(port_str: str) -> int:
        """Parse and validate port number from string."""
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError(f"Port must be 1-65535, got {port}")
            return port
        except ValueError as e:
            raise ValueError(f"Invalid PORT environment variable: {e}")

    # ========================================================================
    # Server Configuration
    # ========================================================================
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = _parse_port.__func__(os.getenv("PORT", "8001"))
    WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", "./workspace")
    AUDIT_LOG_PATH: str = os.getenv("AUDIT_LOG_PATH", "./audit.jsonl")

    # ========================================================================
    # Redis Configuration
    # ========================================================================
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_DB: int = 0
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "100"))
    REDIS_SOCKET_CONNECT_TIMEOUT: float = float(
        os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2")
    )
    REDIS_SOCKET_TIMEOUT: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "2"))

    # ========================================================================
    # Governance Configuration
    # ========================================================================
    DEFAULT_EXECUTION_MODE: str = os.getenv("DEFAULT_MODE", "PERMISSION")
    DEFAULT_ELEVATION_TTL: int = 300  # 5 minutes
    ELICITATION_TIMEOUT: int = 300  # 5 minutes

    # ========================================================================
    # Lease Configuration (Phase 3)
    # ========================================================================
    LEASE_TTL_BY_RISK: dict[str, int] = {
        "safe": 300,  # 5 minutes, 3 calls
        "sensitive": 300,  # 5 minutes, 1 call
        "dangerous": 120,  # 2 minutes, 1 call
    }
    LEASE_CALLS_BY_RISK: dict[str, int] = {"safe": 3, "sensitive": 1, "dangerous": 1}

    # ========================================================================
    # HMAC Secret for Capability Tokens (Phase 4)
    # ========================================================================
    HMAC_SECRET: str = os.getenv(
        "HMAC_SECRET", "default_dev_secret_change_in_production_32bytes_minimum"
    )

    # ========================================================================
    # Progressive Schemas (Phase 5)
    # ========================================================================
    SCHEMA_MIN_TOKEN_BUDGET: int = 50

    # ========================================================================
    # TOON Encoding (Phase 6)
    # ========================================================================
    ENABLE_TOON_OUTPUTS: bool = True
    TOON_TOKEN_THRESHOLD: int = 200
    TOON_ARRAY_THRESHOLD: int = 5

    # ========================================================================
    # Feature Flags (Phase 9)
    # ========================================================================
    ENABLE_SEMANTIC_RETRIEVAL: bool = False  # Phase 2
    ENABLE_LEASE_MANAGEMENT: bool = True  # Phase 3
    ENABLE_PROGRESSIVE_SCHEMAS: bool = False  # Phase 5
    ENABLE_MACROS: bool = True  # Phase 7

    @classmethod
    def validate(cls) -> bool:
        """
        Validate configuration consistency.

        Checks:
        - HMAC_SECRET is set (warning if not)
        - All TTL values are > 0

        Returns:
            True if validation passes

        Raises:
            ValueError: If validation fails
        """
        errors = []

        # Validate HMAC secret
        is_production = os.getenv("ENVIRONMENT", "").lower() == "production"
        is_default_secret = (
            cls.HMAC_SECRET == "default_dev_secret_change_in_production_32bytes_minimum"
        )

        if is_production and (not cls.HMAC_SECRET or is_default_secret):
            errors.append(
                "HMAC_SECRET must be set to a strong secret in production. "
                "The default dev secret is not secure for production use."
            )
        elif not cls.HMAC_SECRET:
            import warnings

            warnings.warn(
                "HMAC_SECRET not set - capability tokens will fail in Phase 4. "
                "Set HMAC_SECRET environment variable for production use."
            )
        elif is_default_secret:
            import warnings
            warnings.warn(
                "HMAC_SECRET is using the default development secret. "
                "Set a unique secret for real deployments."
            )
        elif len(cls.HMAC_SECRET) < 32:
            import warnings

            warnings.warn(
                f"HMAC_SECRET is only {len(cls.HMAC_SECRET)} characters. "
                "For security, use at least 32 characters (256 bits)."
            )

        # Validate TTL values are positive
        for risk, ttl in cls.LEASE_TTL_BY_RISK.items():
            if ttl <= 0:
                errors.append(f"LEASE_TTL_BY_RISK[{risk}] must be > 0, got {ttl}")

        # Validate DEFAULT_ELEVATION_TTL
        if cls.DEFAULT_ELEVATION_TTL <= 0:
            errors.append(f"DEFAULT_ELEVATION_TTL must be > 0, got {cls.DEFAULT_ELEVATION_TTL}")

        # Validate ELICITATION_TIMEOUT
        if cls.ELICITATION_TIMEOUT <= 0:
            errors.append(f"ELICITATION_TIMEOUT must be > 0, got {cls.ELICITATION_TIMEOUT}")

        # Validate Redis settings
        if cls.REDIS_MAX_CONNECTIONS <= 0:
            errors.append(
                f"REDIS_MAX_CONNECTIONS must be > 0, got {cls.REDIS_MAX_CONNECTIONS}"
            )
        if cls.REDIS_SOCKET_CONNECT_TIMEOUT <= 0:
            errors.append(
                "REDIS_SOCKET_CONNECT_TIMEOUT must be > 0, "
                f"got {cls.REDIS_SOCKET_CONNECT_TIMEOUT}"
            )
        if cls.REDIS_SOCKET_TIMEOUT <= 0:
            errors.append(
                f"REDIS_SOCKET_TIMEOUT must be > 0, got {cls.REDIS_SOCKET_TIMEOUT}"
            )

        if errors:
            raise ValueError(f"Config validation failed: {'; '.join(errors)}")

        return True
