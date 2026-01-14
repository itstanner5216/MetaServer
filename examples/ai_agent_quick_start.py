#!/usr/bin/env python3
"""
Quick start example for AI Agent Pipeline.

This script demonstrates how to use the AI agent pipeline to analyze a PR.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.agents.llm_validation_agent import LLMValidationAgent
from scripts.agents.llm_remediation_agent import LLMRemediationAgent
from scripts.agents.llm_architectural_guardian import LLMArchitecturalGuardian
from scripts.agents.llm_functional_verifier import LLMFunctionalVerifier


async def example_single_agent():
    """Example: Run a single agent on a PR."""
    print("=" * 80)
    print("Example 1: Running Single Agent")
    print("=" * 80)
    print()
    
    # Create validator agent in dry-run mode (won't post comments)
    agent = LLMValidationAgent(dry_run=True)
    
    # Mock PR context (in real use, this comes from GitHub API)
    pr_context = {
        "number": 123,
        "title": "Fix: Update validation logic",
        "body": "This PR fixes a bug in the validation logic",
        "changed_files": [
            {
                "filename": "src/validator.py",
                "status": "modified",
                "additions": 15,
                "deletions": 8,
                "patch": """@@ -10,8 +10,15 @@ def validate(data):
-    if not data:
-        return False
+    if data is None:
+        return False
+    
+    if not isinstance(data, dict):
+        raise ValueError("Data must be a dictionary")
+    
     return True"""
            }
        ],
        "diff": "... full diff here ...",
        "base_branch": "main",
        "head_branch": "fix/validation",
        "author": "developer123",
    }
    
    # Build prompt
    prompt = agent.build_user_prompt(pr_context)
    print("Generated Prompt Preview:")
    print(prompt[:500] + "...\n")
    
    # Simulate LLM response
    simulated_response = '''```json
{
  "verdict": "PASS",
  "summary": "Good defensive programming practices. The changes improve null safety and add type checking.",
  "confidence": 0.9,
  "findings": [
    {
      "severity": "info",
      "category": "maintainability",
      "message": "Good use of isinstance() for type checking",
      "file_path": "src/validator.py",
      "line_number": 13,
      "suggestion": "Consider adding more specific error messages"
    }
  ]
}
```'''
    
    # Parse response
    output = agent.parse_response(simulated_response, pr_context["number"])
    
    print("Agent Output:")
    print(f"  Verdict: {output.verdict}")
    print(f"  Summary: {output.summary}")
    print(f"  Confidence: {output.confidence:.0%}")
    print(f"  Findings: {len(output.findings)}")
    print()
    
    # Generate markdown comment
    markdown = output.to_markdown()
    print("Generated Comment Preview:")
    print(markdown[:500] + "...\n")


async def example_all_agents():
    """Example: Run all agents on a PR."""
    print("=" * 80)
    print("Example 2: Running All Agents")
    print("=" * 80)
    print()
    
    agents = [
        ("Validator", LLMValidationAgent),
        ("Remediator", LLMRemediationAgent),
        ("Guardian", LLMArchitecturalGuardian),
        ("Verifier", LLMFunctionalVerifier),
    ]
    
    results = {}
    
    for name, agent_class in agents:
        print(f"\n--- {name} Agent ---")
        agent = agent_class(dry_run=True)
        print(f"Model: {agent.model_config.model}")
        print(f"Provider: {agent.model_config.provider}")
        print(f"System Prompt: {len(agent.system_prompt)} characters")
        
        # Each agent would analyze the PR and return results
        results[name] = {
            "model": agent.model_config.model,
            "provider": agent.model_config.provider,
        }
    
    print("\n" + "=" * 80)
    print("Summary of All Agents")
    print("=" * 80)
    for name, info in results.items():
        print(f"{name}: {info['model']} ({info['provider']})")


async def example_with_api_keys():
    """Example: Check API key configuration."""
    print("=" * 80)
    print("Example 3: API Key Configuration Check")
    print("=" * 80)
    print()
    
    required_keys = {
        "AZURE_OPENAI_API_KEY": "Azure OpenAI (Validator)",
        "GITHUB_MODELS_TOKEN": "GitHub Models (Remediator)",
        "MOONSHOT_API_KEY": "Moonshot (Guardian)",
        "OPENROUTER_API_KEY": "OpenRouter (Verifier)",
    }
    
    print("Checking for required API keys:\n")
    
    all_set = True
    for key, description in required_keys.items():
        is_set = os.environ.get(key) is not None
        status = "✅ Set" if is_set else "❌ Not Set"
        print(f"{status} - {key}")
        print(f"         Used by: {description}")
        if not is_set:
            all_set = False
    
    print()
    if all_set:
        print("✅ All API keys are configured!")
        print("You can run agents with real API calls.")
    else:
        print("⚠️  Some API keys are missing.")
        print("To run agents with real LLM calls, set the missing API keys:")
        print()
        for key, description in required_keys.items():
            if not os.environ.get(key):
                print(f"  export {key}='your-api-key-here'")
        print()
        print("For GitHub Actions, add these as repository secrets.")


async def example_configuration():
    """Example: Show configuration details."""
    print("=" * 80)
    print("Example 4: Configuration Overview")
    print("=" * 80)
    print()
    
    from scripts.agents.llm_config import get_config, AgentRole
    
    config = get_config()
    
    print("Loaded Configuration:\n")
    print(f"Config file: config/models.yaml\n")
    
    for role in AgentRole:
        model_config = config.get_model_config(role)
        print(f"{model_config.display_name}")
        print(f"  Model: {model_config.model}")
        print(f"  Provider: {model_config.provider}")
        print(f"  Endpoint: {model_config.endpoint}")
        print(f"  Temperature: {model_config.temperature}")
        print(f"  Max Tokens: {model_config.max_tokens}")
        print(f"  Timeout: {model_config.timeout}s")
        print()


async def main():
    """Run all examples."""
    print("\n" + "🤖" * 40)
    print("AI Agent Pipeline - Quick Start Examples")
    print("🤖" * 40 + "\n")
    
    # Example 1: Single agent
    await example_single_agent()
    
    # Example 2: All agents
    await example_all_agents()
    
    # Example 3: API keys
    await example_with_api_keys()
    
    # Example 4: Configuration
    await example_configuration()
    
    print("\n" + "=" * 80)
    print("Next Steps:")
    print("=" * 80)
    print()
    print("1. Set up API keys (see Example 3)")
    print("2. Run on a real PR:")
    print("   python -m scripts.agents.run_agent --pr 123 --all --dry-run")
    print("3. Remove --dry-run to post actual comments")
    print("4. Configure GitHub Actions workflow to run automatically")
    print()
    print("📚 Full documentation: docs/AI_AGENT_PIPELINE.md")
    print()


if __name__ == "__main__":
    asyncio.run(main())
