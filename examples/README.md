# AI Agent Pipeline Examples

This directory contains example scripts demonstrating how to use the AI Agent Pipeline.

## Quick Start Example

Run the quick start example to see all features in action:

```bash
python examples/ai_agent_quick_start.py
```

This will demonstrate:
1. Running a single agent
2. Running all agents
3. API key configuration check
4. Configuration overview

## Example Output

The quick start script shows you how agents:
- Parse PR context
- Generate prompts
- Parse LLM responses
- Generate markdown comments

All examples run in dry-run mode (no actual API calls).

## Running Agents on Real PRs

After reviewing the examples, try running agents on actual PRs:

```bash
# Dry-run mode (no comments posted)
python -m scripts.agents.run_agent --pr 123 --all --dry-run

# Run specific agent
python -m scripts.agents.run_agent --pr 123 --agent validator --dry-run

# Post actual comments (requires API keys)
export AZURE_OPENAI_API_KEY='your-key'
export GITHUB_TOKEN='your-github-token'
python -m scripts.agents.run_agent --pr 123 --agent validator
```

## More Information

See the full documentation: [docs/AI_AGENT_PIPELINE.md](../docs/AI_AGENT_PIPELINE.md)
