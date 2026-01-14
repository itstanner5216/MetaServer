# AI Agent Pipeline

Production-ready AI agent pipeline using **4 different LLM models** to review, validate, fix, and verify pull requests.

## 🎯 Overview

This pipeline uses specialized AI agents, each powered by different LLM models, to provide comprehensive PR analysis:

| Agent | Model | Provider | Purpose |
|-------|-------|----------|---------|
| 🔍 Validator | `o4-mini` | Azure OpenAI | Reviews code quality, security, and best practices |
| 🔧 Remediator | `DeepSeek-V3-0324` | GitHub Models | Suggests specific fixes for issues |
| 🏛️ Guardian | `kimi-k2-turbo` | Moonshot | Validates architecture and detects breaking changes |
| ✅ Verifier | `mimo-v2-flash:free` | OpenRouter | Analyzes test coverage and merge readiness |

## 🚀 Quick Start

### 1. Set up API Keys

Add these secrets to your GitHub repository settings:

- `AZURE_OPENAI_API_KEY` - For Validation Agent
- `GITHUB_MODELS_TOKEN` - For Remediation Agent  
- `MOONSHOT_API_KEY` - For Architectural Guardian
- `OPENROUTER_API_KEY` - For Functional Verifier

### 2. Run Agents Locally

```bash
# Run all agents on a PR
python -m scripts.agents.run_agent --pr 123 --all --dry-run

# Run specific agent
python -m scripts.agents.run_agent --pr 123 --agent validator

# Save results to file
python -m scripts.agents.run_agent --pr 123 --all --output results.json
```

### 3. GitHub Actions Integration

The pipeline runs automatically on all PRs via `.github/workflows/ai-agent-pipeline.yml`.

Manual trigger:
```bash
gh workflow run ai-agent-pipeline.yml -f pr_number=123
```

## 🔧 Configuration

All models are configured in `config/models.yaml`. To swap a model, just edit the YAML file:

```yaml
agents:
  validator:
    model: "claude-3-5-sonnet-20241022"  # Changed from o4-mini
    provider: "anthropic"                  # Changed from azure_openai
    endpoint: "https://api.anthropic.com/v1/messages"
    api_key_env: "ANTHROPIC_API_KEY"
```

**No code changes needed!** Just update the YAML and add the corresponding API key secret.

## 📁 File Structure

```
config/
└── models.yaml                         # Model configuration

scripts/agents/
├── llm_config.py                       # Configuration loader
├── llm_client.py                       # Unified LLM client
├── llm_base_agent.py                   # Base agent class
├── llm_validation_agent.py             # Agent 1: Code reviewer
├── llm_remediation_agent.py            # Agent 2: Auto-fixer
├── llm_architectural_guardian.py       # Agent 3: Architecture validator
├── llm_functional_verifier.py          # Agent 4: Test analyzer
└── run_agent.py                        # CLI runner

.github/workflows/
└── ai-agent-pipeline.yml               # GitHub Actions workflow
```

## 🤖 Agent Details

### 🔍 Validation Agent (o4-mini)

**Purpose:** Code quality and security review

**Checks:**
- Code quality and maintainability
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
- Common anti-patterns and bugs
- Performance issues
- Documentation and naming conventions

**Output:** PASS | WARN | FAIL | BLOCK

### 🔧 Remediation Agent (DeepSeek-V3)

**Purpose:** Automated fix suggestions

**Analyzes:**
- Auto-fixable security vulnerabilities
- Common code smells and anti-patterns
- Import errors and dependency issues
- Simple refactoring opportunities
- Type hint additions

**Output:** Specific code snippets (before/after)

### 🏛️ Architectural Guardian (Kimi K2)

**Purpose:** Architecture and API validation

**Evaluates:**
- Breaking API changes
- Architectural violations
- New features vs bug fixes
- Design patterns and SOLID principles
- Backward compatibility

**Output:** SAFE | REVIEW | REJECT

### ✅ Functional Verifier (MiMo-v2)

**Purpose:** Testing and quality assurance

**Analyzes:**
- Test coverage for changes
- Test quality and comprehensiveness
- Edge case coverage
- Regression risk
- Integration concerns

**Output:** ready | needs_tests | needs_review | do_not_merge

## 🔌 Supported Providers

The pipeline supports these LLM providers out of the box:

- **Azure OpenAI** - Enterprise-grade OpenAI models
- **OpenAI** - Direct OpenAI API
- **Anthropic** - Claude models
- **GitHub Models** - GitHub's model marketplace
- **Moonshot** - Kimi/Moonshot AI models
- **OpenRouter** - Access to many models through one API
- **Ollama** - Local model hosting

### Adding a New Provider

1. Add provider config to `config/models.yaml`:

```yaml
providers:
  my_provider:
    auth_header: "Authorization"
    auth_prefix: "Bearer "
    extra_headers:
      X-Custom-Header: "value"
```

2. Update an agent to use the new provider:

```yaml
agents:
  validator:
    provider: "my_provider"
    endpoint: "https://api.myprovider.com/v1/chat"
    api_key_env: "MY_PROVIDER_API_KEY"
```

## 📊 GitHub Actions Workflow

The workflow runs in 4 stages:

1. **Collect PRs** - Identifies target PRs
2. **Run Agents** - Executes all 4 agents in parallel (matrix strategy)
3. **Generate Summary** - Creates consolidated report
4. **Check Status** - Determines overall pass/fail

### Workflow Features

- ✅ Parallel execution for speed
- ✅ Independent agent failures (fail-fast: false)
- ✅ Artifact uploads for results
- ✅ Summary report in GitHub UI
- ✅ Automatic PR comments
- ✅ Exit codes for CI/CD integration

## 🛠️ Development

### Running Tests

```bash
# Test configuration loading
python -c "from scripts.agents.llm_config import get_config; print(get_config())"

# Test agent instantiation
python -c "from scripts.agents.llm_validation_agent import LLMValidationAgent; LLMValidationAgent(dry_run=True)"
```

### Adding a New Agent

1. Create `scripts/agents/llm_my_agent.py`:

```python
from .llm_config import AgentRole
from .llm_base_agent import BaseAgent, AgentOutput

class MyAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.VALIDATOR, **kwargs)
    
    @property
    def system_prompt(self) -> str:
        return "Your system prompt here"
    
    def build_user_prompt(self, pr_context: dict) -> str:
        return f"Analyze PR #{pr_context['number']}"
    
    def parse_response(self, response: str, pr_number: int) -> AgentOutput:
        # Parse LLM response
        return AgentOutput(...)
```

2. Add to `scripts/agents/__init__.py`
3. Add to `run_agent.py` AGENTS dict
4. Update workflow if needed

## 🔒 Security

- API keys are stored as GitHub secrets (never in code)
- Dry-run mode for safe testing
- Read-only GitHub token by default
- No secrets logged or exposed

## 📝 License

See repository LICENSE file.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test your changes with `--dry-run`
4. Submit a pull request

## 💡 Tips

- Use `--dry-run` flag to test without posting comments
- Check `results/*.json` files for detailed agent outputs
- Review GitHub Actions artifacts for full execution logs
- Adjust model parameters in `config/models.yaml` for better results
- Monitor API costs - consider rate limits and usage quotas

## 🐛 Troubleshooting

**Issue: "Missing API key" error**
- Ensure all required secrets are set in GitHub repository settings
- For local testing, set environment variables: `export AZURE_OPENAI_API_KEY=xxx`

**Issue: Agent timeout**
- Increase `timeout` value in `config/models.yaml`
- Check if the LLM provider is experiencing outages

**Issue: Parsing errors**
- Agents expect JSON responses; some models may not comply
- Check `raw_response` field in output for debugging
- Adjust system prompt to emphasize JSON format

**Issue: Rate limiting**
- Increase `retry_delay` in defaults
- Use different models with higher rate limits
- Stagger agent execution instead of parallel

## 📚 Documentation

- [Configuration Reference](config/models.yaml)
- [Agent API Documentation](scripts/agents/)
- [GitHub Actions Workflow](.github/workflows/ai-agent-pipeline.yml)
