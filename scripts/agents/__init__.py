"""AI agents for PR validation and auto-remediation."""

# Legacy workflow agents (test runners, git operations)
from . import validation_agent
from . import remediation_agent
from . import architectural_guardian
from . import functional_verifier
from . import meta_pr_creator
from . import generate_summary

# New LLM-based agents
from .llm_config import AgentRole, AgentConfig, get_config
from .llm_client import LLMClient, ChatMessage, ChatResponse
from .llm_base_agent import BaseAgent, AgentOutput
from .llm_validation_agent import LLMValidationAgent
from .llm_remediation_agent import LLMRemediationAgent
from .llm_architectural_guardian import LLMArchitecturalGuardian
from .llm_functional_verifier import LLMFunctionalVerifier

__all__ = [
    # Legacy agents
    "validation_agent",
    "remediation_agent",
    "architectural_guardian",
    "functional_verifier",
    "meta_pr_creator",
    "generate_summary",
    # LLM agents
    "AgentRole",
    "AgentConfig",
    "get_config",
    "LLMClient",
    "ChatMessage",
    "ChatResponse",
    "BaseAgent",
    "AgentOutput",
    "LLMValidationAgent",
    "LLMRemediationAgent",
    "LLMArchitecturalGuardian",
    "LLMFunctionalVerifier",
]
