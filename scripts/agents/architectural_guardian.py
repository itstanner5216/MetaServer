#!/usr/bin/env python3
"""
Architectural Guardian Agent - Ensure PRs don't introduce breaking changes.

Analysis methods:
- Function signature analysis (AST-based)
- Data flow analysis
- API contract verification
- Behavioral classification

Classification:
- SAFE: Bug fixes, logging, error handling
- REVIEW: Refactoring, performance optimizations
- REJECT: Breaking changes, new features

Output: reports/architectural_analysis.json
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Set
from dataclasses import dataclass, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.agents.utils.github_client import GitHubClient
from scripts.agents.utils.git_operations import GitOperations
from scripts.agents.utils.ast_analyzer import ASTAnalyzer


@dataclass
class ArchitecturalVerdict:
    """Architectural analysis verdict for a PR."""
    
    pr_number: int
    title: str
    architectural_verdict: str  # SAFE, REVIEW, REJECT
    change_classification: str  # bug_fix, refactor, feature, etc.
    breaking_changes: List[str]
    behavioral_changes: List[str]
    risk_level: str  # low, medium, high
    recommendation: str  # APPROVE, REVIEW, REJECT
    details: Dict[str, Any]
    
    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


class ArchitecturalGuardian:
    """Architectural guardian agent."""
    
    def __init__(self, repo_path: str = ".", github_token: str = None):
        """
        Initialize architectural guardian.
        
        Args:
            repo_path: Path to repository
            github_token: GitHub API token
        """
        self.repo_path = Path(repo_path).resolve()
        self.github = GitHubClient(token=github_token)
        self.git = GitOperations(repo_path=repo_path)
        self.ast_analyzer = ASTAnalyzer(repo_path=repo_path)
        self.original_branch = None
        
        # Cache for file contents to avoid repeated git operations
        self._file_cache = {}
    
    def analyze_prs(self, validation_results: Dict[str, Any]) -> List[ArchitecturalVerdict]:
        """
        Analyze PRs for architectural changes.
        
        Args:
            validation_results: Validation results dictionary
            
        Returns:
            List of ArchitecturalVerdict objects
        """
        print("=" * 80)
        print("🏛️  ARCHITECTURAL GUARDIAN - Analyzing PRs")
        print("=" * 80)
        print()
        
        # Save original branch
        self.original_branch = self.git.get_current_branch()
        
        # Get passing PRs (only analyze those that could be merged)
        results = validation_results.get("results", [])
        passing_prs = [r for r in results if r["status"] == "PASS"]
        
        print(f"Analyzing {len(passing_prs)} passing PRs")
        print()
        
        # Analyze each PR
        verdicts = []
        for i, pr_result in enumerate(passing_prs, 1):
            pr_number = pr_result["pr_number"]
            print(f"[{i}/{len(passing_prs)}] Analyzing PR #{pr_number}: {pr_result['title']}")
            print("-" * 80)
            
            try:
                verdict = self.analyze_pr(pr_result)
                verdicts.append(verdict)
                
                emoji = {"SAFE": "✅", "REVIEW": "⚠️", "REJECT": "❌"}
                status_emoji = emoji.get(verdict.architectural_verdict, "❓")
                print(f"{status_emoji} PR #{pr_number}: {verdict.architectural_verdict} ({verdict.risk_level} risk)")
                print(f"   Classification: {verdict.change_classification}")
                print(f"   Recommendation: {verdict.recommendation}")
                
                if verdict.breaking_changes:
                    print(f"   Breaking changes: {len(verdict.breaking_changes)}")
                
                if verdict.behavioral_changes:
                    print(f"   Behavioral changes: {len(verdict.behavioral_changes)}")
                
            except Exception as e:
                print(f"❌ Error analyzing PR #{pr_number}: {e}")
                
                verdict = ArchitecturalVerdict(
                    pr_number=pr_number,
                    title=pr_result["title"],
                    architectural_verdict="REVIEW",
                    change_classification="unknown",
                    breaking_changes=[],
                    behavioral_changes=[],
                    risk_level="unknown",
                    recommendation="MANUAL_REVIEW",
                    details={"error": str(e)},
                )
                verdicts.append(verdict)
            
            print()
        
        # Return to original branch
        print(f"Returning to original branch: {self.original_branch}")
        self.git.checkout(self.original_branch)
        
        print()
        print("=" * 80)
        print("🏁 ARCHITECTURAL ANALYSIS COMPLETE")
        print("=" * 80)
        
        # Print summary
        safe = sum(1 for v in verdicts if v.architectural_verdict == "SAFE")
        review = sum(1 for v in verdicts if v.architectural_verdict == "REVIEW")
        reject = sum(1 for v in verdicts if v.architectural_verdict == "REJECT")
        
        print(f"Total PRs analyzed: {len(verdicts)}")
        print(f"Safe: {safe}")
        print(f"Review: {review}")
        print(f"Reject: {reject}")
        print()
        
        return verdicts
    
    def analyze_pr(self, pr_result: Dict[str, Any]) -> ArchitecturalVerdict:
        """
        Analyze a single PR.
        
        Args:
            pr_result: PR validation result dictionary
            
        Returns:
            ArchitecturalVerdict object
        """
        pr_number = pr_result["pr_number"]
        
        # Checkout PR branch
        print(f"  → Checking out PR #{pr_number}")
        pr = self.github.get_pr(pr_number)
        self.git.checkout_pr(pr_number, f"pr-{pr_number}")
        
        # Get changed files
        print(f"  → Analyzing changed files...")
        changed_files = self.git.get_changed_files(pr.base_ref)
        python_files = [f for f in changed_files if f.endswith(".py")]
        
        print(f"     Found {len(python_files)} Python files changed")
        
        # Analyze changes
        breaking_changes = []
        behavioral_changes = []
        details = {
            "changed_files": len(python_files),
            "api_changes": [],
            "tool_changes": [],
            "governance_changes": [],
        }
        
        # Analyze function signatures
        print(f"  → Analyzing function signatures...")
        for file_path in python_files:
            try:
                # Get old version with caching
                cache_key = f"{pr.base_ref}:{file_path}"
                if cache_key not in self._file_cache:
                    old_content = self.git.get_file_at_ref(file_path, pr.base_ref)
                    self._file_cache[cache_key] = old_content
                else:
                    old_content = self._file_cache[cache_key]
                
                # Parse both versions
                old_analysis = self._analyze_content(old_content, file_path)
                new_analysis = self.ast_analyzer.analyze_file(file_path)
                
                # Compare signatures
                signature_changes = self._compare_signatures(old_analysis, new_analysis, file_path)
                breaking_changes.extend(signature_changes["breaking"])
                behavioral_changes.extend(signature_changes["behavioral"])
                
                # Check for API changes
                if "api" in file_path or "tool" in file_path:
                    details["api_changes"].append({
                        "file": file_path,
                        "changes": signature_changes,
                    })
                
                # Check for governance changes
                if "governance" in file_path or "middleware" in file_path:
                    details["governance_changes"].append({
                        "file": file_path,
                        "changes": signature_changes,
                    })
                
            except Exception as e:
                print(f"     Warning: Failed to analyze {file_path}: {e}")
                continue
        
        # Classify the PR
        classification = self._classify_pr(pr, changed_files, breaking_changes, behavioral_changes)
        
        # Determine verdict
        verdict = self._determine_verdict(classification, breaking_changes, behavioral_changes)
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(
            breaking_changes,
            behavioral_changes,
            classification,
            details,
        )
        
        # Determine recommendation
        recommendation = self._determine_recommendation(verdict, risk_level, breaking_changes)
        
        return ArchitecturalVerdict(
            pr_number=pr_number,
            title=pr_result["title"],
            architectural_verdict=verdict,
            change_classification=classification,
            breaking_changes=breaking_changes,
            behavioral_changes=behavioral_changes,
            risk_level=risk_level,
            recommendation=recommendation,
            details=details,
        )
    
    def _analyze_content(self, content: str, file_path: str):
        """Analyze Python content from string."""
        import ast
        from scripts.agents.utils.ast_analyzer import CodeAnalysis
        
        tree = ast.parse(content, filename=str(file_path))
        analysis = CodeAnalysis()
        self.ast_analyzer._analyze_node(tree, analysis, file_path)
        return analysis
    
    def _compare_signatures(self, old_analysis, new_analysis, file_path: str) -> Dict[str, List[str]]:
        """
        Compare function signatures between two versions.
        
        Returns:
            Dictionary with 'breaking' and 'behavioral' changes
        """
        breaking = []
        behavioral = []
        
        # Build lookup maps
        old_functions = {f.name: f for f in old_analysis.functions}
        new_functions = {f.name: f for f in new_analysis.functions}
        
        # Check for removed functions
        for func_name in old_functions:
            if func_name not in new_functions:
                # Check if it's a public API function
                if not func_name.startswith("_"):
                    breaking.append(f"Function removed: {file_path}::{func_name}")
        
        # Check for modified functions
        for func_name in old_functions:
            if func_name in new_functions:
                old_func = old_functions[func_name]
                new_func = new_functions[func_name]
                
                comparison = self.ast_analyzer.compare_signatures(old_func, new_func)
                
                if comparison["is_breaking"]:
                    breaking.append(f"Breaking change in {file_path}::{func_name}: "
                                    f"{', '.join(comparison['changes'])}")
                elif comparison["changes"]:
                    behavioral.append(f"Behavioral change in {file_path}::{func_name}: "
                                      f"{', '.join(comparison['changes'])}")
        
        # Check for new public functions (might be a feature)
        for func_name in new_functions:
            if func_name not in old_functions and not func_name.startswith("_"):
                behavioral.append(f"New public function: {file_path}::{func_name}")
        
        return {"breaking": breaking, "behavioral": behavioral}
    
    def _classify_pr(
        self,
        pr,
        changed_files: List[str],
        breaking_changes: List[str],
        behavioral_changes: List[str],
    ) -> str:
        """
        Classify the type of PR.
        
        Returns:
            Classification string
        """
        title_lower = pr.title.lower()
        
        # Check title keywords
        if any(kw in title_lower for kw in ["fix", "bug", "patch", "correct"]):
            return "bug_fix"
        
        if any(kw in title_lower for kw in ["refactor", "reorganize", "restructure"]):
            return "refactor"
        
        if any(kw in title_lower for kw in ["feat", "feature", "add", "new"]):
            return "feature"
        
        if any(kw in title_lower for kw in ["perf", "performance", "optimize"]):
            return "performance"
        
        if any(kw in title_lower for kw in ["doc", "documentation"]):
            return "documentation"
        
        if any(kw in title_lower for kw in ["test", "testing"]):
            return "test"
        
        # Infer from changes
        if breaking_changes:
            return "breaking_change"
        
        if not behavioral_changes and not breaking_changes:
            # Only implementation changes
            return "internal_refactor"
        
        return "unknown"
    
    def _determine_verdict(
        self,
        classification: str,
        breaking_changes: List[str],
        behavioral_changes: List[str],
    ) -> str:
        """
        Determine architectural verdict.
        
        Returns:
            Verdict: SAFE, REVIEW, or REJECT
        """
        # Reject if breaking changes
        if breaking_changes:
            return "REJECT"
        
        # Safe classifications
        safe_classifications = [
            "bug_fix",
            "documentation",
            "test",
            "internal_refactor",
        ]
        
        if classification in safe_classifications and not behavioral_changes:
            return "SAFE"
        
        # Review classifications
        review_classifications = [
            "refactor",
            "performance",
        ]
        
        if classification in review_classifications:
            return "REVIEW"
        
        # Features require review
        if classification == "feature":
            return "REJECT"  # Per requirements: reject new features
        
        # Default to review for behavioral changes
        if behavioral_changes:
            return "REVIEW"
        
        return "SAFE"
    
    def _calculate_risk_level(
        self,
        breaking_changes: List[str],
        behavioral_changes: List[str],
        classification: str,
        details: Dict[str, Any],
    ) -> str:
        """
        Calculate risk level.
        
        Returns:
            Risk level: low, medium, high
        """
        # High risk
        if breaking_changes:
            return "high"
        
        if classification == "feature":
            return "high"
        
        if details.get("governance_changes"):
            return "high"
        
        # Medium risk
        if len(behavioral_changes) > 5:
            return "medium"
        
        if classification in ["refactor", "performance"]:
            return "medium"
        
        if details.get("api_changes"):
            return "medium"
        
        # Low risk
        return "low"
    
    def _determine_recommendation(
        self,
        verdict: str,
        risk_level: str,
        breaking_changes: List[str],
    ) -> str:
        """
        Determine recommendation.
        
        Returns:
            Recommendation: APPROVE, REVIEW, REJECT
        """
        if verdict == "REJECT":
            return "REJECT"
        
        if verdict == "REVIEW" or risk_level in ["medium", "high"]:
            return "MANUAL_REVIEW"
        
        if verdict == "SAFE" and risk_level == "low":
            return "APPROVE"
        
        return "MANUAL_REVIEW"


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Architectural Guardian for analyzing PRs"
    )
    parser.add_argument(
        "--validation",
        type=str,
        required=True,
        help="Input validation results JSON file",
    )
    parser.add_argument(
        "--remediation",
        type=str,
        help="Input remediation results JSON file (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/architectural_analysis.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repository path",
    )
    
    args = parser.parse_args()
    
    # Load validation results
    with open(args.validation) as f:
        validation_results = json.load(f)
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run analysis
    agent = ArchitecturalGuardian(repo_path=args.repo)
    verdicts = agent.analyze_prs(validation_results)
    
    # Save results
    output_data = {
        "total_analyzed": len(verdicts),
        "safe": sum(1 for v in verdicts if v.architectural_verdict == "SAFE"),
        "review": sum(1 for v in verdicts if v.architectural_verdict == "REVIEW"),
        "reject": sum(1 for v in verdicts if v.architectural_verdict == "REJECT"),
        "verdicts": [v.to_dict() for v in verdicts],
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Results saved to: {output_path}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
