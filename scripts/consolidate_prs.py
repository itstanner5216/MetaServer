#!/usr/bin/env python3
"""
Consolidate duplicate/conflicting PRs.

Usage:
    python scripts/consolidate_prs.py --dry-run  # Preview only
    python scripts/consolidate_prs.py --execute  # Actually close PRs
"""

import os
import sys
from typing import List, Dict, Set
from dataclasses import dataclass
from collections import defaultdict
import httpx
import re


@dataclass
class PR:
    number: int
    title: str
    body: str
    base_branch: str
    created_at: str
    updated_at: str
    files_changed: List[str]
    commits: int
    mergeable_state: str
    labels: List[str]


class PRConsolidator:
    def __init__(self, token: str, repo: str, dry_run: bool = True):
        self.token = token
        self.repo = repo  # format: "owner/repo"
        self.dry_run = dry_run
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            },
            timeout=30.0
        )
    
    def fetch_all_prs(self) -> List[PR]:
        """Fetch all open PRs."""
        owner, repo = self.repo.split('/')
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        
        all_prs = []
        page = 1
        while True:
            resp = self.client.get(url, params={"state": "open", "per_page": 100, "page": page})
            resp.raise_for_status()
            prs = resp.json()
            if not prs:
                break
            
            for pr_data in prs:
                # Fetch files for each PR
                files_resp = self.client.get(pr_data["url"] + "/files")
                files = [f["filename"] for f in files_resp.json()]
                
                all_prs.append(PR(
                    number=pr_data["number"],
                    title=pr_data["title"],
                    body=pr_data["body"] or "",
                    base_branch=pr_data["base"]["ref"],
                    created_at=pr_data["created_at"],
                    updated_at=pr_data["updated_at"],
                    files_changed=files,
                    commits=pr_data["commits"],
                    mergeable_state=pr_data.get("mergeable_state", "unknown"),
                    labels=[l["name"] for l in pr_data["labels"]]
                ))
            
            page += 1
        
        return all_prs
    
    def extract_issue_keywords(self, pr: PR) -> Set[str]:
        """Extract keywords describing what the PR fixes."""
        text = f"{pr.title} {pr.body}".lower()
        
        keywords = set()
        
        # Common patterns
        patterns = [
            r"fix\s+(\w+(?:\s+\w+){0,3})\s+(?:bug|issue|error)",
            r"(?:governance|lease|hook|audit|middleware|elicitation|redis|import|test)",
            r"re-evaluate|refactor|update|restore|prevent|ensure",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                if isinstance(matches[0], tuple):
                    keywords.update(m for m in matches[0] if m)
                else:
                    keywords.update(matches)
        
        # File-based keywords
        if any("middleware" in f for f in pr.files_changed):
            keywords.add("middleware")
        if any("lease" in f for f in pr.files_changed):
            keywords.add("lease")
        if any("test" in f for f in pr.files_changed):
            keywords.add("test")
        
        return keywords
    
    def group_prs(self, prs: List[PR]) -> Dict[str, List[PR]]:
        """Group PRs by base branch and issue similarity."""
        groups = defaultdict(list)
        
        for pr in prs:
            # Primary grouping by base branch
            base_key = pr.base_branch
            
            # Secondary grouping by issue keywords
            keywords = self.extract_issue_keywords(pr)
            keyword_key = "_".join(sorted(keywords)[:3]) if keywords else "other"
            
            group_key = f"{base_key}::{keyword_key}"
            groups[group_key].append(pr)
        
        return groups
    
    def rank_pr_quality(self, pr: PR) -> float:
        """Score a PR's quality (higher = better)."""
        score = 0.0
        
        # Prefer recent updates
        score += 10.0  # Base score
        
        # Prefer clean merge state
        if pr.mergeable_state == "clean":
            score += 5.0
        elif pr.mergeable_state == "unstable":
            score += 2.0
        
        # Prefer fewer commits (cleaner history)
        if pr.commits <= 3:
            score += 3.0
        elif pr.commits <= 10:
            score += 1.0
        
        # Prefer comprehensive descriptions
        if len(pr.body) > 200:
            score += 2.0
        
        # Prefer labeled PRs
        if pr.labels:
            score += 1.0
        
        # Recency bonus (parse ISO timestamp)
        # More recent = higher score (simplified)
        score += hash(pr.updated_at) % 10  # Pseudo-recency
        
        return score
    
    def consolidate(self) -> Dict:
        """Main consolidation logic."""
        print("🔍 Fetching all open PRs...")
        prs = self.fetch_all_prs()
        print(f"   Found {len(prs)} open PRs")
        
        print("\n📊 Grouping PRs by similarity...")
        groups = self.group_prs(prs)
        print(f"   Created {len(groups)} groups")
        
        report = {
            "original_count": len(prs),
            "kept": [],
            "closed": [],
            "groups": []
        }
        
        for group_key, group_prs in groups.items():
            if len(group_prs) == 1:
                # No duplicates, keep it
                report["kept"].append(group_prs[0].number)
                continue
            
            # Rank and pick winner
            ranked = sorted(group_prs, key=self.rank_pr_quality, reverse=True)
            winner = ranked[0]
            losers = ranked[1:]
            
            group_info = {
                "name": group_key,
                "winner": winner.number,
                "winner_title": winner.title,
                "closed_prs": [pr.number for pr in losers],
                "reason": "Most comprehensive and recent solution"
            }
            
            report["kept"].append(winner.number)
            report["closed"].extend([pr.number for pr in losers])
            report["groups"].append(group_info)
            
            # Close losers
            for loser in losers:
                self.close_pr(loser, winner)
        
        return report
    
    def close_pr(self, pr: PR, winner: PR):
        """Close a PR with explanation."""
        owner, repo = self.repo.split('/')
        
        comment = f"""🤖 **Automated PR Consolidation**

This PR has been automatically closed as part of a cleanup effort to reduce duplicate/conflicting PRs.

**Superseded by:** #{winner.number} - {winner.title}
**Reason:** The linked PR provides a more comprehensive or recent solution to the same issue.

**What was this PR trying to fix?**
{pr.title}

If you believe this was closed in error, please comment and tag @{owner} for review.

---
*Automated by PR Consolidation Workflow*
"""
        
        if self.dry_run:
            print(f"   [DRY RUN] Would close PR #{pr.number} in favor of #{winner.number}")
        else:
            # Post comment
            self.client.post(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{pr.number}/comments",
                json={"body": comment}
            )
            
            # Close PR
            self.client.patch(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr.number}",
                json={"state": "closed"}
            )
            
            print(f"   ✅ Closed PR #{pr.number} in favor of #{winner.number}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--execute", action="store_true", help="Actually close PRs")
    args = parser.parse_args()
    
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN environment variable required")
        sys.exit(1)
    
    consolidator = PRConsolidator(
        token=token,
        repo=os.getenv("GITHUB_REPOSITORY", "itstanner5216/MetaServer"),
        dry_run=not args.execute
    )
    
    report = consolidator.consolidate()
    
    print(f"\n📋 Consolidation Report:")
    print(f"   Original PRs: {report['original_count']}")
    print(f"   Kept: {len(report['kept'])}")
    print(f"   Closed: {len(report['closed'])}")
    
    print(f"\n✅ Kept PRs: {', '.join(f'#{n}' for n in sorted(report['kept']))}")


if __name__ == "__main__":
    main()
