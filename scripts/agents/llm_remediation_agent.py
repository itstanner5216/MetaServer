#!/usr/bin/env python3
"""
LLM-based Remediation Agent - Uses AI to suggest fixes.
Agent 2: Auto-Fixer (uses DeepSeek-V3 via GitHub Models)
"""

import json
import re
from .llm_config import AgentRole
from .llm_base_agent import BaseAgent, AgentOutput


class LLMRemediationAgent(BaseAgent):
    """AI-powered code remediation agent."""
    
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.REMEDIATOR, **kwargs)
    
    @property
    def system_prompt(self) -> str:
        """Return the system prompt for code remediation."""
        return """You are an expert software engineer specializing in automated code fixes and refactoring.

Your task is to analyze pull requests and suggest specific, actionable fixes for any issues found.

Focus on:
1. Auto-fixable security vulnerabilities
2. Common code smells and anti-patterns
3. Import errors and dependency issues
4. Simple refactoring opportunities
5. Type hint additions

Provide your analysis in JSON format with this structure:
{
  "verdict": "PASS" | "WARN" | "FAIL" | "BLOCK",
  "summary": "Brief assessment of fixability",
  "confidence": 0.0-1.0,
  "findings": [
    {
      "severity": "info" | "warning" | "error" | "critical",
      "category": "auto-fixable" | "manual-review" | "refactoring",
      "message": "Description of the issue",
      "file_path": "path/to/file.py",
      "line_number": 123,
      "suggestion": "How to fix it"
    }
  ],
  "suggested_fixes": [
    {
      "file": "path/to/file.py",
      "description": "Brief description of fix",
      "before": "old code snippet",
      "after": "new code snippet"
    }
  ]
}

Verdict guide:
- PASS: No fixes needed
- WARN: Some improvements possible but not critical
- FAIL: Issues that should be fixed
- BLOCK: Critical issues that must be fixed immediately

Only suggest fixes you're confident about. Be specific with code snippets."""
    
    def build_user_prompt(self, pr_context: dict) -> str:
        """Build user prompt with PR details."""
        prompt = f"""Analyze this pull request and suggest fixes:

**PR #{pr_context['number']}: {pr_context['title']}**

**Description:**
{pr_context['body'] or 'No description provided'}

**Changed Files ({len(pr_context['changed_files'])} files):**
"""
        
        for f in pr_context['changed_files']:
            prompt += f"\n- {f['filename']} (+{f['additions']}/-{f['deletions']})"
            if f.get('patch'):
                prompt += f"\n```diff\n{f['patch'][:1000]}\n```\n"
        
        prompt += "\n\nProvide your remediation analysis in the JSON format specified in your system prompt."
        prompt += "\nInclude specific code snippets in the 'before' and 'after' fields for each suggested fix."
        
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
            
            return AgentOutput(
                pr_number=pr_number,
                agent_role=self.role.value,
                verdict=data.get("verdict", "WARN"),
                summary=data.get("summary", "Remediation analysis completed"),
                findings=data.get("findings", []),
                suggested_fixes=data.get("suggested_fixes", []),
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
