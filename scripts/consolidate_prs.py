#!/usr/bin/env python3
"""
Analyze open PRs, identify duplicates, and close redundant ones.
Keeps the best PR from each group based on:
- Code quality (fewer changes, cleaner implementation)
- Recency (newer PRs likely incorporate learnings)
- Base branch (prefer PRs to main)
- Test coverage
"""

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Dict
from collections import defaultdict
import json

# Add agents utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agents', 'utils'))
from github_client import GitHubClient


@dataclass
class PRAnalysis:
    number: int
    title: str
    base_branch: str
    created_at: str
    updated_at: str
    files_changed: int
    additions: int
    deletions: int
    body: str
    head_branch: str
    labels: List[str]
    
    @property
    def issue_signature(self) -> str:
        """Extract the core issue this PR addresses."""
        # Remove PR numbers, common prefixes, and normalize
        normalized = self.title.lower()
        normalized = re.sub(r'#\d+', '', normalized)
        normalized = re.sub(r'\b(fix|update|add|remove|refactor|improve)\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Also check body for Codex task patterns
        if 'Codex Task' in self.body:
            # Extract the actual issue description from the motivation section
            motivation_match = re.search(r'### Motivation\s*\n\s*[-*]\s*(.+?)(?:\n\n|\n###)', self.body, re.DOTALL)
            if motivation_match:
                normalized += ' ' + motivation_match.group(1).lower()[:100]
        
        return normalized
    
    @property
    def quality_score(self) -> float:
        """Score PR quality (higher is better)."""
        score = 0.0
        
        # Prefer PRs to main
        if self.base_branch == 'main':
            score += 10.0
        
        # Prefer smaller, focused changes
        total_changes = self.additions + self.deletions
        if total_changes < 100:
            score += 5.0
        elif total_changes < 500:
            score += 2.0
        
        # Prefer recent PRs (they likely incorporate learnings)
        # This is a simplified heuristic
        score += 1.0
        
        # Prefer PRs with tests
        if 'test' in self.body.lower() or any('test' in label for label in self.labels):
            score += 3.0
        
        # Penalize PRs with "no automated tests were executed"
        if 'no automated tests were executed' in self.body.lower():
            score -= 2.0
        
        return score


def fetch_open_prs(github_client: GitHubClient) -> List[PRAnalysis]:
    """Fetch all open PRs from the repository."""
    prs = []
    
    # Use existing client method
    pr_objects = github_client.get_open_prs(state='open')
    
    for pr in pr_objects:
        # Get detailed info for each PR
        details = github_client.get_pr_details(pr.number)
        
        analysis = PRAnalysis(
            number=pr.number,
            title=pr.title,
            base_branch=pr.base_ref,
            created_at=pr.created_at,
            updated_at=pr.updated_at,
            files_changed=details.get('changed_files', 0),
            additions=details.get('additions', 0),
            deletions=details.get('deletions', 0),
            body=details.get('body') or '',
            head_branch=pr.head_ref,
            labels=pr.labels
        )
        prs.append(analysis)
    
    return prs


def group_duplicate_prs(prs: List[PRAnalysis]) -> Dict[str, List[PRAnalysis]]:
    """Group PRs by the issue they're addressing."""
    groups = defaultdict(list)
    
    for pr in prs:
        # Group by issue signature AND base branch (PRs to different branches can coexist)
        key = f"{pr.base_branch}::{pr.issue_signature}"
        groups[key].append(pr)
    
    # Only keep groups with 2+ PRs (actual duplicates)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def select_best_pr(group: List[PRAnalysis]) -> PRAnalysis:
    """Select the best PR from a group of duplicates."""
    return max(group, key=lambda pr: pr.quality_score)


def close_duplicate_prs(repo_name: str, github_token: str, dry_run: bool = True):
    """Main function to analyze and close duplicate PRs."""
    print(f"🔍 Analyzing PRs in {repo_name}...")
    
    # Initialize GitHub client
    github_client = GitHubClient(token=github_token, repo=repo_name)
    
    prs = fetch_open_prs(github_client)
    print(f"Found {len(prs)} open PRs")
    
    groups = group_duplicate_prs(prs)
    print(f"Identified {len(groups)} groups of duplicate PRs")
    
    if not groups:
        print("✅ No duplicate PRs found!")
        return
    
    summary = {
        'total_prs': len(prs),
        'duplicate_groups': len(groups),
        'prs_to_close': 0,
        'prs_to_keep': 0,
        'groups': []
    }
    
    for group_key, duplicate_prs in groups.items():
        base_branch, signature = group_key.split('::', 1)
        print(f"\n📦 Group: {signature[:60]}... (base: {base_branch})")
        print(f"   Found {len(duplicate_prs)} duplicate PRs:")
        
        best_pr = select_best_pr(duplicate_prs)
        
        group_info = {
            'signature': signature,
            'base_branch': base_branch,
            'best_pr': best_pr.number,
            'closed_prs': []
        }
        
        for pr in duplicate_prs:
            status = "✅ KEEP" if pr.number == best_pr.number else "❌ CLOSE"
            print(f"   #{pr.number} - {status} (score: {pr.quality_score:.1f}) - {pr.title[:60]}")
            
            if pr.number != best_pr.number:
                group_info['closed_prs'].append(pr.number)
                summary['prs_to_close'] += 1
                
                # Close the PR
                if not dry_run:
                    comment = f"""## 🤖 Automated PR Consolidation

This PR has been automatically closed as a **duplicate**.

**Reason:** This PR addresses the same issue as #{best_pr.number}, which has been selected as the primary PR for this fix.

**Primary PR:** #{best_pr.number} - {best_pr.title}

**Why #{best_pr.number} was selected:**
- Quality score: {best_pr.quality_score:.1f} vs {pr.quality_score:.1f}
- Base branch: {best_pr.base_branch}
- Changes: {best_pr.additions + best_pr.deletions} lines

If you believe this was closed in error, please comment and we'll review.

---
*This action was performed by the PR Consolidation workflow*
"""
                    github_client.add_comment(pr.number, comment)
                    github_client.close_pr(pr.number)
                    print(f"      → Closed #{pr.number}")
            else:
                summary['prs_to_keep'] += 1
        
        summary['groups'].append(group_info)
    
    # Save summary
    summary_file = 'pr_consolidation_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, indent=2, fp=f)
    
    print(f"\n" + "="*60)
    print(f"📊 Summary:")
    print(f"   Total PRs analyzed: {summary['total_prs']}")
    print(f"   Duplicate groups found: {summary['duplicate_groups']}")
    print(f"   PRs to keep: {summary['prs_to_keep']}")
    print(f"   PRs to close: {summary['prs_to_close']}")
    print(f"   Final PR count: {summary['total_prs'] - summary['prs_to_close']}")
    
    if dry_run:
        print(f"\n⚠️  DRY RUN MODE - No PRs were actually closed")
        print(f"   Run with --execute to apply changes")
    else:
        print(f"\n✅ Consolidation complete!")
    
    print(f"\n📄 Full summary saved to: {summary_file}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Consolidate duplicate PRs')
    parser.add_argument('--repo', required=True, help='Repository (owner/name)')
    parser.add_argument('--token', help='GitHub token (or use GITHUB_TOKEN env var)')
    parser.add_argument('--execute', action='store_true', help='Actually close PRs (default is dry-run)')
    
    args = parser.parse_args()
    
    token = args.token or os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError("GitHub token required (--token or GITHUB_TOKEN env var)")
    
    close_duplicate_prs(
        repo_name=args.repo,
        github_token=token,
        dry_run=not args.execute
    )
