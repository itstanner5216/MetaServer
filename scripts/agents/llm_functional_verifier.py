#!/usr/bin/env python3
"""
LLM-based Functional Verifier - Uses AI to analyze test results.
Agent 4: Test Analyzer (uses MiMo-v2-Flash via OpenRouter)
"""

import json
import re
from .llm_config import AgentRole
from .llm_base_agent import BaseAgent, AgentOutput


class LLMFunctionalVerifier(BaseAgent):
    """AI-powered functional verification agent."""
    
    def __init__(self, **kwargs):
        super().__init__(role=AgentRole.VERIFIER, **kwargs)
    
    @property
    def system_prompt(self) -> str:
        """Return the system prompt for functional verification."""
        return """You are a QA expert specializing in test analysis and functional verification.

Your task is to analyze pull requests from a testing and quality perspective.

Evaluate:
1. Test coverage - Are new features tested?
2. Test quality - Are tests meaningful and comprehensive?
3. Edge cases - Are edge cases covered?
4. Regression risk - Could this break existing functionality?
5. Integration concerns - How does this affect the system?

Provide your analysis in JSON format with this structure:
{
  "verdict": "PASS" | "WARN" | "FAIL" | "BLOCK",
  "summary": "Brief testing assessment",
  "confidence": 0.0-1.0,
  "merge_readiness": "ready" | "needs_tests" | "needs_review" | "do_not_merge",
  "findings": [
    {
      "severity": "info" | "warning" | "error" | "critical",
      "category": "coverage" | "test_quality" | "edge_cases" | "regression_risk",
      "message": "Description of the issue",
      "file_path": "path/to/file.py",
      "suggestion": "What tests are needed or how to improve"
    }
  ]
}

Verdict guide:
- PASS: Well tested, good coverage, low regression risk, ready to merge
- WARN: Acceptable but could use more tests, needs review
- FAIL: Insufficient testing, missing critical tests
- BLOCK: High regression risk or no tests for critical changes

Merge readiness guide:
- ready: Safe to merge immediately
- needs_tests: Should add more tests before merge
- needs_review: Requires manual review before merge
- do_not_merge: Critical issues, must not merge

Be practical but thorough. Consider the scope and risk of changes."""
    
    def build_user_prompt(self, pr_context: dict) -> str:
        """Build user prompt with PR details."""
        prompt = f"""Analyze the testing and quality aspects of this pull request:

**PR #{pr_context['number']}: {pr_context['title']}**

**Description:**
{pr_context['body'] or 'No description provided'}

**Changed Files ({len(pr_context['changed_files'])} files):**
"""
        
        test_files = []
        code_files = []
        
        for f in pr_context['changed_files']:
            fname = f['filename']
            if 'test' in fname.lower() or fname.endswith('_test.py'):
                test_files.append(f)
            else:
                code_files.append(f)
            prompt += f"\n- {fname} (+{f['additions']}/-{f['deletions']})"
        
        prompt += f"\n\n**Summary:**"
        prompt += f"\n- Code files changed: {len(code_files)}"
        prompt += f"\n- Test files changed: {len(test_files)}"
        
        if code_files:
            prompt += f"\n\n**Code Changes:**"
            for f in code_files[:5]:  # Limit to first 5
                if f.get('patch'):
                    prompt += f"\n\n{f['filename']}:\n```diff\n{f['patch'][:1500]}\n```"
        
        if test_files:
            prompt += f"\n\n**Test Changes:**"
            for f in test_files[:5]:  # Limit to first 5
                if f.get('patch'):
                    prompt += f"\n\n{f['filename']}:\n```diff\n{f['patch'][:1500]}\n```"
        
        prompt += "\n\nProvide your functional verification analysis in the JSON format specified."
        prompt += "\nFocus on whether the changes are adequately tested and safe to merge."
        
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
            
            merge_readiness = data.get("merge_readiness", "needs_review")
            summary = f"{merge_readiness} - {data.get('summary', 'Analysis completed')}"
            
            return AgentOutput(
                pr_number=pr_number,
                agent_role=self.role.value,
                verdict=data.get("verdict", "WARN"),
                summary=summary,
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
