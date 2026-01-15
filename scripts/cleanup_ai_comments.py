#!/usr/bin/env python3
"""
Delete AI review pipeline comments from PRs.

Usage:
    python scripts/cleanup_ai_comments.py --prs 12,34,56  # Specific PRs
    python scripts/cleanup_ai_comments.py --all            # All open PRs
    python scripts/cleanup_ai_comments.py --dry-run        # Preview
"""

import os
import sys
import httpx
from typing import List


class CommentCleaner:
    def __init__(self, token: str, repo: str, dry_run: bool = True):
        self.token = token
        self.repo = repo
        self.dry_run = dry_run
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            },
            timeout=30.0
        )
    
    def is_ai_review_comment(self, comment: dict) -> bool:
        """Check if comment is from AI review pipeline."""
        body = comment.get("body", "")
        user = comment.get("user", {}).get("login", "")
        
        # Match AI pipeline markers
        markers = [
            "AI-Powered PR Review Pipeline",
            "🔍 Validation Agent",
            "🔧 Remediation Agent",
            "🏛️ Architectural Guardian",
            "✅ Functional Verifier"
        ]
        
        return (
            user == "github-actions[bot]" and
            any(marker in body for marker in markers)
        )
    
    def cleanup_pr(self, pr_number: int) -> int:
        """Delete AI comments from a PR, return count deleted."""
        owner, repo = self.repo.split('/')
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        
        resp = self.client.get(url, params={"per_page": 100})
        resp.raise_for_status()
        comments = resp.json()
        
        deleted_count = 0
        for comment in comments:
            if self.is_ai_review_comment(comment):
                if self.dry_run:
                    print(f"   [DRY RUN] Would delete comment {comment['id']} from PR #{pr_number}")
                else:
                    delete_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment['id']}"
                    self.client.delete(delete_url)
                    print(f"   🗑️  Deleted comment {comment['id']} from PR #{pr_number}")
                
                deleted_count += 1
        
        return deleted_count
    
    def cleanup_all(self, pr_numbers: List[int]):
        """Clean up multiple PRs."""
        total_deleted = 0
        
        for pr_num in pr_numbers:
            print(f"\n🧹 Cleaning PR #{pr_num}...")
            count = self.cleanup_pr(pr_num)
            total_deleted += count
            print(f"   Deleted {count} comments")
        
        print(f"\n✅ Total comments deleted: {total_deleted}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prs", help="Comma-separated PR numbers")
    parser.add_argument("--all", action="store_true", help="Clean all open PRs")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN required")
        sys.exit(1)
    
    cleaner = CommentCleaner(
        token=token,
        repo=os.getenv("GITHUB_REPOSITORY", "itstanner5216/MetaServer"),
        dry_run=args.dry_run
    )
    
    if args.all:
        # Fetch all open PRs
        owner, repo = cleaner.repo.split('/')
        resp = cleaner.client.get(f"https://api.github.com/repos/{owner}/{repo}/pulls", params={"state": "open", "per_page": 100})
        prs = [pr["number"] for pr in resp.json()]
    elif args.prs:
        prs = [int(n.strip()) for n in args.prs.split(",")]
    else:
        print("❌ Must specify --prs or --all")
        sys.exit(1)
    
    cleaner.cleanup_all(prs)


if __name__ == "__main__":
    main()
