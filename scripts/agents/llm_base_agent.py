"""
Abstract base class for all AI agents.
"""

import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from .llm_config import AgentRole, get_config
from .llm_client import LLMClient, ChatMessage


@dataclass
class AgentOutput:
    """Structured output from an agent."""
    pr_number: int
    agent_role: str
    verdict: str  # PASS, WARN, FAIL, BLOCK
    summary: str
    findings: list = field(default_factory=list)
    suggested_fixes: list = field(default_factory=list)
    confidence: float = 0.0
    raw_response: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_markdown(self) -> str:
        """Convert output to markdown for PR comment."""
        config = get_config()
        model_config = config.get_model_config(AgentRole(self.agent_role))
        
        emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "BLOCK": "🚫"}.get(self.verdict, "❓")
        
        md = f"## {emoji} {model_config.display_name} Results\n\n"
        md += f"**Model:** `{model_config.model}` ({model_config.provider})\n"
        md += f"**Verdict:** {self.verdict}\n\n"
        md += f"**Summary:** {self.summary}\n\n"
        
        if self.findings:
            md += "### Findings\n\n"
            for finding in self.findings:
                sev_emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚫"}.get(
                    finding.get("severity", "info"), "•"
                )
                md += f"- {sev_emoji} **{finding.get('category', 'General')}**: {finding.get('message', '')}\n"
                if finding.get("file_path"):
                    md += f"  - File: `{finding['file_path']}`"
                    if finding.get("line_number"):
                        md += f" (line {finding['line_number']})"
                    md += "\n"
                if finding.get("suggestion"):
                    md += f"  - 💡 {finding['suggestion']}\n"
        
        if self.suggested_fixes:
            md += "\n### Suggested Fixes\n\n"
            for fix in self.suggested_fixes:
                md += f"- **{fix.get('file', 'Unknown')}**: {fix.get('description', '')}\n"
        
        md += f"\n---\n*Confidence: {self.confidence:.0%}*\n"
        
        return md


class BaseAgent(ABC):
    """
    Abstract base for all AI agents.
    
    Each agent:
    1. Receives PR context (diff, files, metadata)
    2. Builds a role-specific prompt
    3. Calls LLM via unified client (configured via models.yaml)
    4. Parses response into structured output
    5. Takes action (comment, push fix, label)
    """
    
    def __init__(
        self,
        role: AgentRole,
        repo_owner: str = "itstanner5216",
        repo_name: str = "MetaServer",
        dry_run: bool = False,
    ):
        if httpx is None:
            raise ImportError(
                "httpx is required for agents. "
                "Install it with: pip install httpx"
            )
        
        self.role = role
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.dry_run = dry_run
        self.client = LLMClient(role)
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.config = get_config()
        self.model_config = self.config.get_model_config(role)
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass
    
    @abstractmethod
    def build_user_prompt(self, pr_context: dict) -> str:
        """Build user prompt with PR-specific context."""
        pass
    
    @abstractmethod
    def parse_response(self, response: str, pr_number: int) -> AgentOutput:
        """Parse LLM response into structured output."""
        pass
    
    async def get_pr_context(self, pr_number: int) -> dict:
        """Fetch PR details from GitHub API."""
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        async with httpx.AsyncClient() as client:
            # Get PR details
            pr_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}"
            pr_response = await client.get(pr_url, headers=headers)
            pr_response.raise_for_status()
            pr_data = pr_response.json()
            
            # Get PR diff
            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_response = await client.get(pr_url, headers=diff_headers)
            diff = diff_response.text if diff_response.status_code == 200 else ""
            
            # Get changed files
            files_url = f"{pr_url}/files"
            files_response = await client.get(files_url, headers=headers)
            files_data = files_response.json() if files_response.status_code == 200 else []
        
        return {
            "number": pr_number,
            "title": pr_data["title"],
            "body": pr_data.get("body", ""),
            "diff": diff[:50000] if len(diff) > 50000 else diff,
            "changed_files": [
                {
                    "filename": f["filename"],
                    "status": f["status"],
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    "patch": f.get("patch", "")[:5000],
                }
                for f in files_data[:20]  # Limit files
            ],
            "base_branch": pr_data["base"]["ref"],
            "head_branch": pr_data["head"]["ref"],
            "author": pr_data["user"]["login"],
        }
    
    async def post_comment(self, pr_number: int, body: str) -> None:
        """Post a comment on the PR."""
        if self.dry_run:
            print(f"[DRY RUN] Would post comment to PR #{pr_number}:")
            print(body[:500] + "..." if len(body) > 500 else body)
            return
        
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_number}/comments"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json={"body": body})
            response.raise_for_status()
    
    async def run(self, pr_number: int) -> AgentOutput:
        """Execute agent workflow."""
        print(f"[{self.model_config.display_name}] Starting analysis of PR #{pr_number}")
        print(f"[{self.model_config.display_name}] Using model: {self.model_config.model}")
        
        # Fetch PR context
        pr_context = await self.get_pr_context(pr_number)
        print(f"[{self.model_config.display_name}] Fetched PR: {pr_context['title']}")
        
        # Build messages
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=self.build_user_prompt(pr_context)),
        ]
        
        # Call LLM
        print(f"[{self.model_config.display_name}] Calling {self.model_config.model}...")
        response = await self.client.chat_with_retry(messages)
        print(f"[{self.model_config.display_name}] Received response")
        
        # Parse response
        output = self.parse_response(response.content, pr_number)
        output.raw_response = response.content
        
        # Post comment
        comment_body = output.to_markdown()
        await self.post_comment(pr_number, comment_body)
        print(f"[{self.model_config.display_name}] Posted comment to PR #{pr_number}")
        
        return output
