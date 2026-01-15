#!/usr/bin/env python3
"""
LLM-based Architectural Guardian - Uses AI to validate architecture.
Agent 3: Design Validator (uses Kimi K2 Turbo via Moonshot)
"""

import json
import re
from .llm_config import AgentRole
from .llm_base_agent import BaseAgent, AgentOutput


class LLMArchitecturalGuardian(BaseAgent):
    """AI-powered architectural validation agent."""
    
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.GUARDIAN, **kwargs)
    
    @property
    def system_prompt(self) -> str:
        """Return the system prompt for architectural validation."""
        return """You are a senior software architect specializing in system design and API design.

Your task is to review pull requests for architectural integrity and breaking changes.

Analyze:
1. Breaking API changes (function signature changes, removed functions)
2. Architectural violations (layering, separation of concerns)
3. New features vs bug fixes (reject features, accept bug fixes)
4. Design patterns and SOLID principles
5. Backward compatibility

Provide your analysis in JSON format with this structure:
{
  "verdict": "SAFE" | "REVIEW" | "REJECT",
  "summary": "Brief architectural assessment",
  "confidence": 0.0-1.0,
  "classification": "bug_fix" | "refactor" | "feature" | "breaking_change" | "documentation",
  "risk_level": "low" | "medium" | "high",
  "findings": [
    {
      "severity": "info" | "warning" | "error" | "critical",
      "category": "breaking_change" | "architecture" | "design" | "compatibility",
      "message": "Description of the issue",
      "file_path": "path/to/file.py",
      "suggestion": "How to address it"
    }
  ]
}

Verdict guide:
- SAFE: Bug fix or internal refactor, no breaking changes, low risk
- REVIEW: Refactoring or performance optimization, needs review
- REJECT: Breaking changes, new features, or high-risk changes

Classification guide:
- bug_fix: Fixes a bug without changing APIs
- refactor: Improves code without changing behavior
- feature: Adds new functionality (should be REJECT)
- breaking_change: Changes or removes public APIs (should be REJECT)
- documentation: Only documentation changes (should be SAFE)

Be strict about breaking changes and new features."""
    
    def build_user_prompt(self, pr_context: dict) -> str:
        """Build user prompt with PR details."""
        prompt = f"""Perform an architectural review of this pull request:

**PR #{pr_context['number']}: {pr_context['title']}**

**Description:**
{pr_context['body'] or 'No description provided'}

**Author:** {pr_context['author']}
**Base Branch:** {pr_context['base_branch']}
**Head Branch:** {pr_context['head_branch']}

**Changed Files ({len(pr_context['changed_files'])} files):**
"""
        
        for f in pr_context['changed_files']:
            prompt += f"\n- {f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']})"
        
        prompt += f"\n\n**Diff:**\n```diff\n{pr_context['diff'][:30000]}\n```"
        
        prompt += "\n\nProvide your architectural analysis in the JSON format specified."
        prompt += "\nClassify this change and identify any breaking changes or architectural issues."
        
        return prompt
    
    def parse_response(self, response: str, pr_number: int) -> AgentOutput:
        """Parse LLM response into structured output."""
        try:
            # Look for JSON block
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try to parse entire response as JSON
                data = json.loads(response)
            
            # Map verdict to standard format
            verdict_map = {
                "SAFE": "PASS",
                "REVIEW": "WARN",
                "REJECT": "BLOCK",
            }
            verdict = verdict_map.get(data.get("verdict", "REVIEW"), "WARN")
            
            return AgentOutput(
                pr_number=pr_number,
                agent_role=self.role.value,
                verdict=verdict,
                summary=f"{data.get('classification', 'unknown')} - {data.get('summary', 'Analysis completed')}",
                findings=data.get("findings", []),
                suggested_fixes=[],
                confidence=data.get("confidence", 0.8),
            )
        except (json.JSONDecodeError, AttributeError) as e:
            # Fallback
            return AgentOutput(
                pr_number=pr_number,
                agent_role=self.role.value,
                verdict="WARN",
                summary="Unable to parse structured response",
                findings=[{
                    "severity": "warning",
                    "category": "parsing",
                    "message": f"Response parsing failed: {str(e)}",
                }],
                suggested_fixes=[],
                confidence=0.5,
                raw_response=response,
            )
