#!/usr/bin/env python3
"""GitHub API client for agent operations."""

import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import httpx


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""
    
    number: int
    title: str
    state: str
    head_ref: str
    head_sha: str
    base_ref: str
    base_sha: str
    user: str
    created_at: str
    updated_at: str
    mergeable: Optional[bool] = None
    mergeable_state: Optional[str] = None
    draft: bool = False
    labels: List[str] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = []


class GitHubClient:
    """GitHub API client wrapper."""
    
    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub API token (defaults to GITHUB_TOKEN env var)
            repo: Repository in format "owner/repo" (defaults to GITHUB_REPOSITORY env var)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required (GITHUB_TOKEN env var or token parameter)")
        
        # Get repo from parameter or environment variable
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "itstanner5216/MetaServer")
        self.owner, self.repo_name = self.repo.split("/")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """
        Make a GitHub API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{endpoint}"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()
            
            # Handle empty responses
            if response.status_code == 204:
                return None
                
            return response.json()
    
    def get_open_prs(self, state: str = "open") -> List[PullRequest]:
        """
        Fetch all open pull requests.
        
        Args:
            state: PR state filter (open, closed, all)
            
        Returns:
            List of PullRequest objects
        """
        prs = []
        page = 1
        per_page = 100
        
        while True:
            endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls"
            params = {
                "state": state,
                "page": page,
                "per_page": per_page,
            }
            
            response = self._request("GET", endpoint, params=params)
            
            if not response:
                break
                
            for pr_data in response:
                pr = PullRequest(
                    number=pr_data["number"],
                    title=pr_data["title"],
                    state=pr_data["state"],
                    head_ref=pr_data["head"]["ref"],
                    head_sha=pr_data["head"]["sha"],
                    base_ref=pr_data["base"]["ref"],
                    base_sha=pr_data["base"]["sha"],
                    user=pr_data["user"]["login"],
                    created_at=pr_data["created_at"],
                    updated_at=pr_data["updated_at"],
                    mergeable=pr_data.get("mergeable"),
                    mergeable_state=pr_data.get("mergeable_state"),
                    draft=pr_data.get("draft", False),
                    labels=[label["name"] for label in pr_data.get("labels", [])],
                )
                prs.append(pr)
            
            # Check if there are more pages
            if len(response) < per_page:
                break
                
            page += 1
        
        return prs
    
    def get_pr(self, pr_number: int) -> PullRequest:
        """
        Get a specific pull request.
        
        Args:
            pr_number: PR number
            
        Returns:
            PullRequest object
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"
        pr_data = self._request("GET", endpoint)
        
        return PullRequest(
            number=pr_data["number"],
            title=pr_data["title"],
            state=pr_data["state"],
            head_ref=pr_data["head"]["ref"],
            head_sha=pr_data["head"]["sha"],
            base_ref=pr_data["base"]["ref"],
            base_sha=pr_data["base"]["sha"],
            user=pr_data["user"]["login"],
            created_at=pr_data["created_at"],
            updated_at=pr_data["updated_at"],
            mergeable=pr_data.get("mergeable"),
            mergeable_state=pr_data.get("mergeable_state"),
            draft=pr_data.get("draft", False),
            labels=[label["name"] for label in pr_data.get("labels", [])],
        )
    
    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> int:
        """
        Create a new pull request.
        
        Args:
            title: PR title
            body: PR description
            head: Head branch name
            base: Base branch name (default: main)
            draft: Whether to create as draft PR
            
        Returns:
            Created PR number
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls"
        data = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        
        response = self._request("POST", endpoint, json=data)
        return response["number"]
    
    def update_pr(self, pr_number: int, title: Optional[str] = None, body: Optional[str] = None):
        """
        Update a pull request.
        
        Args:
            pr_number: PR number
            title: New title (optional)
            body: New body (optional)
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"
        data = {}
        
        if title:
            data["title"] = title
        if body:
            data["body"] = body
            
        self._request("PATCH", endpoint, json=data)
    
    def add_comment(self, pr_number: int, comment: str):
        """
        Add a comment to a pull request.
        
        Args:
            pr_number: PR number
            comment: Comment text
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/issues/{pr_number}/comments"
        data = {"body": comment}
        self._request("POST", endpoint, json=data)
    
    def create_branch(self, branch_name: str, sha: str):
        """
        Create a new branch.
        
        Args:
            branch_name: Name of the new branch
            sha: Commit SHA to branch from
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/git/refs"
        data = {
            "ref": f"refs/heads/{branch_name}",
            "sha": sha,
        }
        self._request("POST", endpoint, json=data)
    
    def delete_branch(self, branch_name: str):
        """
        Delete a branch.
        
        Args:
            branch_name: Name of the branch to delete
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/git/refs/heads/{branch_name}"
        self._request("DELETE", endpoint)
    
    def get_file_content(self, path: str, ref: str = "main") -> str:
        """
        Get file content from repository.
        
        Args:
            path: File path in repository
            ref: Git reference (branch, tag, or commit SHA)
            
        Returns:
            File content as string
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/contents/{path}"
        params = {"ref": ref}
        
        response = self._request("GET", endpoint, params=params)
        
        # Decode base64 content
        import base64
        content = base64.b64decode(response["content"]).decode("utf-8")
        return content
    
    def close_pr(self, pr_number: int) -> bool:
        """
        Close a pull request.
        
        Args:
            pr_number: PR number to close
            
        Returns:
            True if successful
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"
        data = {"state": "closed"}
        self._request("PATCH", endpoint, json=data)
        return True
    
    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """
        Get detailed PR information including stats.
        
        Args:
            pr_number: PR number
            
        Returns:
            Dictionary with PR details
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"
        return self._request("GET", endpoint)
    
    def get_pr_comments(self, pr_number: int) -> List[Dict[str, Any]]:
        """
        Get all comments on a PR.
        
        Args:
            pr_number: PR number
            
        Returns:
            List of comment dictionaries
        """
        comments = []
        page = 1
        per_page = 100
        
        while True:
            endpoint = f"/repos/{self.owner}/{self.repo_name}/issues/{pr_number}/comments"
            params = {"page": page, "per_page": per_page}
            
            response = self._request("GET", endpoint, params=params)
            
            if not response:
                break
            
            comments.extend(response)
            
            if len(response) < per_page:
                break
            
            page += 1
        
        return comments
    
    def delete_comment(self, comment_id: int):
        """
        Delete a comment.
        
        Args:
            comment_id: Comment ID to delete
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/issues/comments/{comment_id}"
        self._request("DELETE", endpoint)
