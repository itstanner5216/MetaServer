"""
Agent configuration loader.
Loads models.yaml and provides typed configuration objects.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class AgentRole(str, Enum):
    """Available agent roles."""
    VALIDATOR = "validator"
    REMEDIATOR = "remediator"
    GUARDIAN = "guardian"
    VERIFIER = "verifier"


@dataclass
class ProviderConfig:
    """Provider-specific configuration."""
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    extra_headers: dict = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Configuration for a single agent's model."""
    display_name: str
    description: str
    model: str
    provider: str
    endpoint: str
    api_key_env: str
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    
    def get_api_key(self) -> str:
        """Get API key from environment variable."""
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(
                f"Missing API key: Set {self.api_key_env} environment variable"
            )
        return key


class AgentConfig:
    """
    Central configuration manager.
    Loads from config/models.yaml for easy model swapping.
    """
    
    _instance: Optional["AgentConfig"] = None
    _config: dict = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        # Find config file (check multiple locations)
        possible_paths = [
            Path("config/models.yaml"),
            Path("../config/models.yaml"),
            Path(__file__).parent.parent.parent / "config" / "models.yaml",
        ]
        
        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        
        if config_path is None:
            # Use default configuration if file not found
            self._config = self._default_config()
            return
        
        with open(config_path) as f:
            self._config = yaml.safe_load(f)
    
    def _default_config(self) -> dict:
        """Return default configuration if YAML not found."""
        return {
            "agents": {
                "validator": {
                    "display_name": "🔍 Validation Agent",
                    "description": "Reviews PRs for code quality",
                    "model": "o4-mini",
                    "provider": "azure_openai",
                    "endpoint": "https://myproject5216.openai.azure.com/openai/v1/chat/completions",
                    "api_key_env": "AZURE_OPENAI_API_KEY",
                },
                "remediator": {
                    "display_name": "🔧 Remediation Agent",
                    "description": "Auto-fixes common issues",
                    "model": "DeepSeek-V3-0324",
                    "provider": "github_models",
                    "endpoint": "https://models.inference.ai.azure.com/chat/completions",
                    "api_key_env": "MODELS_API_TOKEN",
                },
                "guardian": {
                    "display_name": "🏛️ Architectural Guardian",
                    "description": "Validates architecture",
                    "model": "kimi-k2-turbo",
                    "provider": "moonshot",
                    "endpoint": "https://api.moonshot.ai/v1/chat/completions",
                    "api_key_env": "MOONSHOT_API_KEY",
                },
                "verifier": {
                    "display_name": "✅ Functional Verifier",
                    "description": "Analyzes test results",
                    "model": "xiaomi/mimo-v2-flash:free",
                    "provider": "openrouter",
                    "endpoint": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key_env": "OPENROUTER_API_KEY",
                },
            },
            "defaults": {
                "temperature": 0.3,
                "max_tokens": 4096,
                "timeout": 120,
                "max_retries": 3,
                "retry_delay": 2.0,
            },
            "providers": {},
        }
    
    def get_model_config(self, role: AgentRole) -> ModelConfig:
        """Get model configuration for an agent role."""
        agent_config = self._config["agents"].get(role.value, {})
        defaults = self._config.get("defaults", {})
        
        # Merge defaults with agent-specific config
        merged = {**defaults, **agent_config}
        
        return ModelConfig(
            display_name=merged.get("display_name", role.value.title()),
            description=merged.get("description", ""),
            model=merged["model"],
            provider=merged["provider"],
            endpoint=merged["endpoint"],
            api_key_env=merged["api_key_env"],
            temperature=merged.get("temperature", 0.3),
            max_tokens=merged.get("max_tokens", 4096),
            timeout=merged.get("timeout", 120),
        )
    
    def get_provider_config(self, provider: str) -> ProviderConfig:
        """Get provider-specific configuration."""
        providers = self._config.get("providers", {})
        provider_config = providers.get(provider, {})
        
        return ProviderConfig(
            auth_header=provider_config.get("auth_header", "Authorization"),
            auth_prefix=provider_config.get("auth_prefix", "Bearer "),
            extra_headers=provider_config.get("extra_headers", {}),
        )
    
    def get_defaults(self) -> dict:
        """Get default settings."""
        return self._config.get("defaults", {})
    
    @classmethod
    def reload(cls) -> None:
        """Force reload configuration from file."""
        cls._instance = None
        cls()


# Convenience function
def get_config() -> AgentConfig:
    """Get the global configuration instance."""
    return AgentConfig()
