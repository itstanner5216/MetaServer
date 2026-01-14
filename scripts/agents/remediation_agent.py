#!/usr/bin/env python3
"""
Remediation Agent - Auto-fix common PR failures.

Capabilities:
- Auto-fix merge conflicts
- Patch test failures
- Fix import errors
- Apply security fixes
- Auto-commit fixes to PR branches

Input: reports/validation_results.json
Output: reports/remediation_results.json
"""

import sys
import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.agents.utils.github_client import GitHubClient
from scripts.agents.utils.git_operations import GitOperations
from scripts.agents.utils.test_runner import TestRunner
from scripts.agents.utils.ast_analyzer import ASTAnalyzer


@dataclass
class RemediationResult:
    """Remediation result for a PR."""
    
    pr_number: int
    original_status: str
    fixes_applied: List[str]
    new_status: str
    success: bool
    errors: List[str]
    
    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


class RemediationAgent:
    """Auto-remediation agent for PR failures."""
    
    def __init__(self, repo_path: str = ".", github_token: str = None, auto_commit: bool = False):
        """
        Initialize remediation agent.
        
        Args:
            repo_path: Path to repository
            github_token: GitHub API token
            auto_commit: Whether to auto-commit fixes
        """
        self.repo_path = Path(repo_path).resolve()
        self.github = GitHubClient(token=github_token)
        self.git = GitOperations(repo_path=repo_path)
        self.test_runner = TestRunner(repo_path=repo_path)
        self.ast_analyzer = ASTAnalyzer(repo_path=repo_path)
        self.auto_commit = auto_commit
        self.original_branch = None
    
    def remediate_failures(self, validation_results: Dict[str, Any]) -> List[RemediationResult]:
        """
        Remediate failed PRs.
        
        Args:
            validation_results: Validation results dictionary
            
        Returns:
            List of RemediationResult objects
        """
        print("=" * 80)
        print("🔧 REMEDIATION AGENT - Starting Auto-Remediation")
        print("=" * 80)
        print()
        
        # Save original branch
        self.original_branch = self.git.get_current_branch()
        
        # Get failed PRs
        results = validation_results.get("results", [])
        failed_prs = [r for r in results if r["status"] == "FAIL"]
        
        print(f"Found {len(failed_prs)} failed PRs to remediate")
        print()
        
        # Remediate each PR
        remediation_results = []
        for i, pr_result in enumerate(failed_prs, 1):
            pr_number = pr_result["pr_number"]
            print(f"[{i}/{len(failed_prs)}] Remediating PR #{pr_number}")
            print("-" * 80)
            
            try:
                result = self.remediate_pr(pr_result)
                remediation_results.append(result)
                
                status_emoji = "✅" if result.success else "❌"
                print(f"{status_emoji} PR #{pr_number}: {len(result.fixes_applied)} fixes applied")
                
                if result.fixes_applied:
                    print(f"   Fixes: {', '.join(result.fixes_applied)}")
                
                if result.errors:
                    print(f"   Errors: {', '.join(result.errors)}")
                
            except Exception as e:
                print(f"❌ Error remediating PR #{pr_number}: {e}")
                
                result = RemediationResult(
                    pr_number=pr_number,
                    original_status="FAIL",
                    fixes_applied=[],
                    new_status="FAIL",
                    success=False,
                    errors=[f"Remediation error: {str(e)}"],
                )
                remediation_results.append(result)
            
            print()
        
        # Return to original branch
        print(f"Returning to original branch: {self.original_branch}")
        self.git.checkout(self.original_branch)
        
        print()
        print("=" * 80)
        print("🏁 REMEDIATION COMPLETE")
        print("=" * 80)
        
        # Print summary
        successful = sum(1 for r in remediation_results if r.success)
        print(f"Total PRs remediated: {len(remediation_results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(remediation_results) - successful}")
        print()
        
        return remediation_results
    
    def remediate_pr(self, pr_result: Dict[str, Any]) -> RemediationResult:
        """
        Remediate a single PR.
        
        Args:
            pr_result: PR validation result dictionary
            
        Returns:
            RemediationResult object
        """
        pr_number = pr_result["pr_number"]
        failure_reasons = pr_result.get("failure_reasons", [])
        fixes_applied = []
        errors = []
        
        # Checkout PR branch
        print(f"  → Checking out PR #{pr_number}")
        try:
            pr = self.github.get_pr(pr_number)
            self.git.checkout_pr(pr_number, f"pr-{pr_number}")
        except Exception as e:
            errors.append(f"Failed to checkout: {e}")
            return RemediationResult(
                pr_number=pr_number,
                original_status=pr_result["status"],
                fixes_applied=fixes_applied,
                new_status="FAIL",
                success=False,
                errors=errors,
            )
        
        # Fix merge conflicts
        if pr_result.get("conflicts"):
            print("  → Fixing merge conflicts...")
            if self._fix_merge_conflicts(pr):
                fixes_applied.append("Resolved merge conflicts")
            else:
                errors.append("Failed to resolve merge conflicts")
        
        # Fix import errors
        if any("import" in reason.lower() or "module" in reason.lower() for reason in failure_reasons):
            print("  → Fixing import errors...")
            fixed = self._fix_import_errors()
            if fixed:
                fixes_applied.append(f"Fixed {len(fixed)} import errors")
        
        # Fix test failures
        if pr_result.get("tests", {}).get("failed", 0) > 0:
            print("  → Attempting to fix test failures...")
            test_fixes = self._fix_test_failures()
            if test_fixes:
                fixes_applied.extend(test_fixes)
        
        # Fix security issues
        security = pr_result.get("security", {})
        if security.get("critical", 0) > 0 or security.get("high", 0) > 0:
            print("  → Fixing security issues...")
            sec_fixes = self._fix_security_issues()
            if sec_fixes:
                fixes_applied.extend(sec_fixes)
        
        # Commit fixes if auto-commit enabled
        if fixes_applied and self.auto_commit:
            print("  → Committing fixes...")
            try:
                self.git.add_all()
                commit_msg = f"fix: auto-remediation by AI agent\n\nFixes applied:\n"
                for fix in fixes_applied:
                    commit_msg += f"- {fix}\n"
                
                self.git.commit(commit_msg)
                
                # Push to PR branch
                print("  → Pushing fixes to remote...")
                self.git.push(f"pr-{pr_number}")
                
                fixes_applied.append("Committed and pushed fixes")
            except Exception as e:
                errors.append(f"Failed to commit fixes: {e}")
        
        # Determine new status
        success = len(fixes_applied) > 0 and len(errors) == 0
        new_status = "FIXED" if success else "PARTIAL" if fixes_applied else "FAIL"
        
        return RemediationResult(
            pr_number=pr_number,
            original_status=pr_result["status"],
            fixes_applied=fixes_applied,
            new_status=new_status,
            success=success,
            errors=errors,
        )
    
    def _fix_merge_conflicts(self, pr) -> bool:
        """
        Fix merge conflicts.
        
        Args:
            pr: PullRequest object
            
        Returns:
            True if conflicts resolved
        """
        try:
            # Get conflicted files
            conflicts = self.git.get_merge_conflicts()
            
            if not conflicts:
                return True
            
            # Try to resolve conflicts automatically
            for conflict_file in conflicts:
                # For simple cases, prefer incoming changes
                try:
                    self.git.resolve_conflict_with_theirs(conflict_file)
                except Exception:
                    # If that fails, try ours
                    try:
                        self.git.resolve_conflict_with_ours(conflict_file)
                    except Exception:
                        return False
            
            return True
        except Exception:
            return False
    
    def _fix_import_errors(self) -> List[str]:
        """
        Fix import errors.
        
        Returns:
            List of fixed import paths
        """
        fixed = []
        
        # Find Python files
        python_files = list(self.repo_path.rglob("*.py"))
        
        for file_path in python_files:
            try:
                # Skip certain directories
                if any(part in file_path.parts for part in [".git", "__pycache__", ".venv", "venv"]):
                    continue
                
                # Read file
                with open(file_path) as f:
                    content = f.read()
                
                original_content = content
                
                # Fix src.meta_mcp imports
                content = re.sub(
                    r'from src\.meta_mcp',
                    'from meta_mcp',
                    content
                )
                content = re.sub(
                    r'import src\.meta_mcp',
                    'import meta_mcp',
                    content
                )
                
                # Write back if changed
                if content != original_content:
                    with open(file_path, "w") as f:
                        f.write(content)
                    
                    fixed.append(str(file_path.relative_to(self.repo_path)))
            except Exception:
                continue
        
        return fixed
    
    def _fix_test_failures(self) -> List[str]:
        """
        Attempt to fix test failures.
        
        Returns:
            List of fixes applied
        """
        fixes = []
        
        # Run tests to get failure patterns
        try:
            result = self.test_runner.run_tests(verbose=True)
            patterns = self.test_runner.get_failure_patterns(result)
            
            for pattern in patterns:
                if pattern["type"] == "import_error":
                    # Import errors are handled separately
                    continue
                
                elif pattern["type"] == "fixture_error":
                    # Try to fix fixture scope issues
                    if self._fix_fixture_errors(pattern):
                        fixes.append(f"Fixed fixture error in {pattern['test']}")
                
                elif pattern["type"] == "assertion_error":
                    # Log assertion errors but don't auto-fix
                    # (too risky to change test expectations)
                    pass
        except Exception:
            pass
        
        return fixes
    
    def _fix_fixture_errors(self, pattern: Dict[str, Any]) -> bool:
        """
        Fix fixture errors.
        
        Args:
            pattern: Failure pattern dictionary
            
        Returns:
            True if fixed
        """
        # This would require sophisticated test file parsing
        # For now, return False (manual fix required)
        return False
    
    def _fix_security_issues(self) -> List[str]:
        """
        Fix security issues.
        
        Returns:
            List of fixes applied
        """
        fixes = []
        
        try:
            # Run Bandit scan
            scan_result = self.test_runner.run_security_scan()
            
            for issue in scan_result.get("issues", []):
                # Fix hardcoded passwords
                if "B105" in issue.get("test_id", ""):
                    if self._fix_hardcoded_password(issue):
                        fixes.append(f"Fixed hardcoded password in {issue['filename']}")
                
                # Fix SQL injection
                elif "B608" in issue.get("test_id", ""):
                    if self._fix_sql_injection(issue):
                        fixes.append(f"Fixed SQL injection in {issue['filename']}")
        except Exception:
            pass
        
        return fixes
    
    def _fix_hardcoded_password(self, issue: Dict[str, Any]) -> bool:
        """Fix hardcoded password."""
        # Requires manual inspection - too risky to auto-fix
        return False
    
    def _fix_sql_injection(self, issue: Dict[str, Any]) -> bool:
        """Fix SQL injection vulnerability."""
        # Requires manual inspection - too risky to auto-fix
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Remediation Agent for auto-fixing PR failures")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input validation results JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/remediation_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repository path",
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Automatically commit and push fixes",
    )
    
    args = parser.parse_args()
    
    # Load validation results
    with open(args.input) as f:
        validation_results = json.load(f)
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run remediation
    agent = RemediationAgent(repo_path=args.repo, auto_commit=args.auto_commit)
    results = agent.remediate_failures(validation_results)
    
    # Save results
    output_data = {
        "total_remediated": len(results),
        "successful": sum(1 for r in results if r.success),
        "partial": sum(1 for r in results if r.new_status == "PARTIAL"),
        "failed": sum(1 for r in results if r.new_status == "FAIL"),
        "results": [r.to_dict() for r in results],
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Results saved to: {output_path}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
