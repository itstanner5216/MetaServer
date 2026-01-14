"""
Tests for LLM-based AI agents.
"""

import pytest
from scripts.agents.llm_config import AgentRole, get_config
from scripts.agents.llm_client import LLMClient, ChatMessage
from scripts.agents.llm_validation_agent import LLMValidationAgent
from scripts.agents.llm_remediation_agent import LLMRemediationAgent
from scripts.agents.llm_architectural_guardian import LLMArchitecturalGuardian
from scripts.agents.llm_functional_verifier import LLMFunctionalVerifier


class TestLLMConfig:
    """Test configuration loading."""
    
    def test_config_loads(self):
        """Test that configuration loads successfully."""
        config = get_config()
        assert config is not None
    
    def test_all_agents_configured(self):
        """Test that all 4 agents are configured."""
        config = get_config()
        
        for role in AgentRole:
            model_config = config.get_model_config(role)
            assert model_config.model is not None
            assert model_config.provider is not None
            assert model_config.endpoint is not None
            assert model_config.api_key_env is not None
    
    def test_validator_config(self):
        """Test validator agent configuration."""
        config = get_config()
        model_config = config.get_model_config(AgentRole.VALIDATOR)
        
        assert model_config.model == "o4-mini"
        assert model_config.provider == "azure_openai"
        assert model_config.api_key_env == "AZURE_OPENAI_API_KEY"
    
    def test_remediator_config(self):
        """Test remediator agent configuration."""
        config = get_config()
        model_config = config.get_model_config(AgentRole.REMEDIATOR)
        
        assert model_config.model == "DeepSeek-V3-0324"
        assert model_config.provider == "github_models"
        assert model_config.api_key_env == "GITHUB_MODELS_TOKEN"
    
    def test_guardian_config(self):
        """Test guardian agent configuration."""
        config = get_config()
        model_config = config.get_model_config(AgentRole.GUARDIAN)
        
        assert model_config.model == "kimi-k2-turbo"
        assert model_config.provider == "moonshot"
        assert model_config.api_key_env == "MOONSHOT_API_KEY"
    
    def test_verifier_config(self):
        """Test verifier agent configuration."""
        config = get_config()
        model_config = config.get_model_config(AgentRole.VERIFIER)
        
        assert model_config.model == "xiaomi/mimo-v2-flash:free"
        assert model_config.provider == "openrouter"
        assert model_config.api_key_env == "OPENROUTER_API_KEY"
    
    def test_provider_configs(self):
        """Test provider-specific configurations."""
        config = get_config()
        
        # Test Azure OpenAI provider
        azure_config = config.get_provider_config("azure_openai")
        assert azure_config.auth_header == "api-key"
        assert azure_config.auth_prefix == ""
        
        # Test OpenRouter provider
        openrouter_config = config.get_provider_config("openrouter")
        assert openrouter_config.auth_header == "Authorization"
        assert openrouter_config.auth_prefix == "Bearer "
        assert "HTTP-Referer" in openrouter_config.extra_headers


class TestLLMClient:
    """Test LLM client."""
    
    def test_client_instantiation(self):
        """Test that client can be instantiated for all roles."""
        for role in AgentRole:
            client = LLMClient(role)
            assert client.role == role
            assert client.model_config is not None
            assert client.provider_config is not None
    
    def test_build_headers(self):
        """Test header building (without API key)."""
        # This will fail on get_api_key, but we can test the structure
        client = LLMClient(AgentRole.VALIDATOR)
        
        # Headers should include content-type
        # We can't test auth headers without API keys
        assert client.provider_config.auth_header == "api-key"
    
    def test_build_payload(self):
        """Test payload building."""
        client = LLMClient(AgentRole.VALIDATOR)
        
        messages = [
            ChatMessage(role="system", content="You are a helpful assistant"),
            ChatMessage(role="user", content="Hello"),
        ]
        
        payload = client._build_payload(messages)
        
        assert payload["model"] == "o4-mini"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["content"] == "Hello"
        assert "temperature" in payload
        assert "max_tokens" in payload


class TestLLMAgents:
    """Test LLM-based agents."""
    
    def test_validation_agent_instantiation(self):
        """Test validation agent instantiation."""
        agent = LLMValidationAgent(dry_run=True)
        assert agent.role == AgentRole.VALIDATOR
        assert agent.dry_run is True
        assert len(agent.system_prompt) > 0
    
    def test_remediation_agent_instantiation(self):
        """Test remediation agent instantiation."""
        agent = LLMRemediationAgent(dry_run=True)
        assert agent.role == AgentRole.REMEDIATOR
        assert agent.dry_run is True
        assert len(agent.system_prompt) > 0
    
    def test_guardian_agent_instantiation(self):
        """Test guardian agent instantiation."""
        agent = LLMArchitecturalGuardian(dry_run=True)
        assert agent.role == AgentRole.GUARDIAN
        assert agent.dry_run is True
        assert len(agent.system_prompt) > 0
    
    def test_verifier_agent_instantiation(self):
        """Test verifier agent instantiation."""
        agent = LLMFunctionalVerifier(dry_run=True)
        assert agent.role == AgentRole.VERIFIER
        assert agent.dry_run is True
        assert len(agent.system_prompt) > 0
    
    def test_validation_agent_prompt_building(self):
        """Test validation agent prompt building."""
        agent = LLMValidationAgent(dry_run=True)
        
        pr_context = {
            "number": 123,
            "title": "Test PR",
            "body": "Test description",
            "changed_files": [
                {"filename": "test.py", "additions": 10, "deletions": 5}
            ],
            "diff": "diff content",
        }
        
        prompt = agent.build_user_prompt(pr_context)
        assert "PR #123" in prompt
        assert "Test PR" in prompt
        assert "test.py" in prompt
    
    def test_validation_agent_response_parsing(self):
        """Test validation agent response parsing."""
        agent = LLMValidationAgent(dry_run=True)
        
        # Test JSON response
        response = '''```json
{
  "verdict": "PASS",
  "summary": "Code looks good",
  "confidence": 0.9,
  "findings": []
}
```'''
        
        output = agent.parse_response(response, 123)
        assert output.pr_number == 123
        assert output.verdict == "PASS"
        assert output.summary == "Code looks good"
        assert output.confidence == 0.9
    
    def test_validation_agent_fallback_parsing(self):
        """Test validation agent fallback parsing."""
        agent = LLMValidationAgent(dry_run=True)
        
        # Test non-JSON response (should fall back gracefully)
        response = "This is just plain text, not JSON"
        
        output = agent.parse_response(response, 123)
        assert output.pr_number == 123
        assert output.verdict == "WARN"
        assert "Unable to parse" in output.summary
    
    def test_remediation_agent_response_parsing(self):
        """Test remediation agent response parsing."""
        agent = LLMRemediationAgent(dry_run=True)
        
        response = '''```json
{
  "verdict": "WARN",
  "summary": "Some fixes needed",
  "confidence": 0.85,
  "findings": [],
  "suggested_fixes": [
    {
      "file": "test.py",
      "description": "Fix import",
      "before": "import old",
      "after": "import new"
    }
  ]
}
```'''
        
        output = agent.parse_response(response, 123)
        assert output.pr_number == 123
        assert output.verdict == "WARN"
        assert len(output.suggested_fixes) == 1
        assert output.suggested_fixes[0]["file"] == "test.py"
    
    def test_guardian_verdict_mapping(self):
        """Test guardian agent verdict mapping."""
        agent = LLMArchitecturalGuardian(dry_run=True)
        
        # Test SAFE -> PASS mapping
        response = '''```json
{
  "verdict": "SAFE",
  "summary": "No breaking changes",
  "confidence": 0.9,
  "classification": "bug_fix",
  "risk_level": "low",
  "findings": []
}
```'''
        
        output = agent.parse_response(response, 123)
        assert output.verdict == "PASS"  # SAFE maps to PASS
    
    def test_verifier_merge_readiness(self):
        """Test verifier agent merge readiness."""
        agent = LLMFunctionalVerifier(dry_run=True)
        
        response = '''```json
{
  "verdict": "PASS",
  "summary": "Well tested",
  "confidence": 0.95,
  "merge_readiness": "ready",
  "findings": []
}
```'''
        
        output = agent.parse_response(response, 123)
        assert output.verdict == "PASS"
        assert "ready" in output.summary
    
    def test_agent_markdown_output(self):
        """Test agent markdown output generation."""
        agent = LLMValidationAgent(dry_run=True)
        
        response = '''```json
{
  "verdict": "WARN",
  "summary": "Minor issues found",
  "confidence": 0.8,
  "findings": [
    {
      "severity": "warning",
      "category": "maintainability",
      "message": "Function too long",
      "file_path": "src/test.py",
      "line_number": 42,
      "suggestion": "Split into smaller functions"
    }
  ]
}
```'''
        
        output = agent.parse_response(response, 123)
        markdown = output.to_markdown()
        
        assert "🔍 Validation Agent" in markdown
        assert "o4-mini" in markdown
        assert "WARN" in markdown
        assert "Minor issues found" in markdown
        assert "Function too long" in markdown
        assert "src/test.py" in markdown
