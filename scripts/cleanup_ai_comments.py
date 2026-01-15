#!/usr/bin/env python3
"""
Delete automated AI review comments from PRs.
Only removes comments from the github-actions bot containing specific patterns.
"""

import os
import sys
from typing import List, Optional

# Add agents utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agents', 'utils'))
from github_client import GitHubClient


def cleanup_ai_comments(repo_name: str, github_token: str, pr_numbers: Optional[List[int]] = None, dry_run: bool = True):
    """Remove AI review comments from specified PRs (or all open PRs)."""
    github_client = GitHubClient(token=github_token, repo=repo_name)
    
    # Get PRs to clean
    if pr_numbers:
        prs = [github_client.get_pr(num) for num in pr_numbers]
    else:
        prs = github_client.get_open_prs(state='open')
    
    print(f"🧹 Cleaning AI comments from {len(prs)} PRs...")
    
    ai_comment_patterns = [
        'AI-Powered PR Review Pipeline',
        'Validation Agent Review',
        'Remediation Agent',
        'Architectural Guardian',
        'Functional Verifier Results'
    ]
    
    total_deleted = 0
    
    for pr in prs:
        pr_deleted = 0
        comments = github_client.get_pr_comments(pr.number)
        
        for comment in comments:
            # Only delete comments from github-actions bot
            if comment.get('user', {}).get('login') == 'github-actions[bot]':
                # Check if it's an AI review comment
                body = comment.get('body', '')
                if any(pattern in body for pattern in ai_comment_patterns):
                    if not dry_run:
                        github_client.delete_comment(comment['id'])
                    pr_deleted += 1
                    total_deleted += 1
        
        if pr_deleted > 0:
            status = "would delete" if dry_run else "deleted"
            print(f"  PR #{pr.number}: {status} {pr_deleted} AI comments")
    
    print(f"\n{'📊' if dry_run else '✅'} Total: {total_deleted} comments {('would be ' if dry_run else '')}deleted")
    
    if dry_run:
        print("⚠️  DRY RUN MODE - Run with --execute to actually delete comments")
    
    return total_deleted


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up AI review comments')
    parser.add_argument('--repo', required=True, help='Repository (owner/name)')
    parser.add_argument('--token', help='GitHub token (or use GITHUB_TOKEN env var)')
    parser.add_argument('--prs', help='Comma-separated PR numbers (default: all open PRs)')
    parser.add_argument('--execute', action='store_true', help='Actually delete comments')
    
    args = parser.parse_args()
    
    token = args.token or os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError("GitHub token required")
    
    pr_numbers = [int(n.strip()) for n in args.prs.split(',')] if args.prs else None
    
    cleanup_ai_comments(
        repo_name=args.repo,
        github_token=token,
        pr_numbers=pr_numbers,
        dry_run=not args.execute
    )
