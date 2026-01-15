#!/usr/bin/env python3
"""
LLM-based Validation Agent - Uses AI to review code quality.
Agent 1: Code Quality Reviewer (uses o4-mini via Azure OpenAI)
"""

import json
import re
from .llm_config import AgentRole
from .llm_base_agent import BaseAgent, AgentOutput


class LLMValidationAgent(BaseAgent):
    """AI-powered code quality validation agent."""
    
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.VALIDATOR, **kwargs)
    
    @property
    def system_prompt(self) -> str:
        """Return the system prompt for code validation."""
        return """You are an expert code reviewer specializing in Python, security, and best practices.

Your task is to analyze pull requests and provide detailed feedback on:
1. Code quality and maintainability
2. Security vulnerabilities (SQL injection, XSS, hardcoded secrets, etc.)
3. Common anti-patterns and bugs
4. Performance issues
5. Documentation and naming conventions

Provide your analysis in JSON format with this structure:
{
  "verdict": "PASS" | "WARN" | "FAIL" | "BLOCK",
  "summary": "Brief overall assessment",
  "confidence": 0.0-1.0,
  "findings": [
    {
      "severity": "info" | "warning" | "error" | "critical",
      "category": "security" | "performance" | "maintainability" | "bugs",
      "message": "Description of the issue",
      "file_path": "path/to/file.py",
      "line_number": 123,
      "suggestion": "How to fix it"
    }
  ]
}

Verdict guide:
- PASS: No significant issues, ready to merge
- WARN: Minor issues that should be addressed but don't block merge
- FAIL: Significant issues that should be fixed before merge
- BLOCK: Critical security or correctness issues that must be fixed

Be thorough but fair. Focus on actionable feedback."""
    
    def build_user_prompt(self, pr_context: dict) -> str:
        """Build user prompt with PR details."""
        prompt = f"""Please review this pull request:

**PR #{pr_context['number']}: {pr_context['title']}**

**Description:**
{pr_context['body'] or 'No description provided'}

**Changed Files ({len(pr_context['changed_files'])} files):**
"""
        
        for f in pr_context['changed_files']:
            prompt += f"\n- {f['filename']} (+{f['additions']}/-{f['deletions']})"
        
        prompt += f"\n\n**Diff:**\n```diff\n{pr_context['diff']}\n```"
        
        prompt += "\n\nProvide your analysis in the JSON format specified in your system prompt."
        
        return prompt
    
    def parse_response(self, response: str, pr_number: int) -> AgentOutput:
        """Parse LLM response into structured output."""
        # Try to extract JSON from the response
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
                summary=data.get("summary", "Analysis completed"),
                findings=data.get("findings", []),
                suggested_fixes=[],
                confidence=data.get("confidence", 0.8),
            )
        except (json.JSONDecodeError, AttributeError) as e:
            # Fallback: create a WARN verdict with the raw response
            return AgentOutput(
                pr_number=pr_number,
                agent_role=self.role.value,
                verdict="WARN",
                summary="Unable to parse structured response",
                findings=[{
                    "severity": "warning",
                    "category": "parsing",
                    "message": f"Response parsing failed: {str(e)}. See raw response.",
                }],
                suggested_fixes=[],
                confidence=0.5,
                raw_response=response,
            )
