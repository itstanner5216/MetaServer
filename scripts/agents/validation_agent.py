#!/usr/bin/env python3
"""
Validation Agent - Sequential PR validation orchestrator.

Validates all open PRs by:
- Checking out PR branch
- Running pytest suite with coverage
- Running Bandit security scanner
- Checking for merge conflicts
- Running invariant validator
- Verifying pre-commit hooks

Outputs: reports/validation_results.json
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.agents.utils.github_client import GitHubClient, PullRequest
from scripts.agents.utils.git_operations import GitOperations
from scripts.agents.utils.test_runner import TestRunner


@dataclass
class ValidationResult:
    """PR validation result."""
    
    pr_number: int
    title: str
    status: str  # PASS or FAIL
    tests: Dict[str, Any]
    security: Dict[str, int]
    conflicts: bool
    invariants: str  # PASS or FAIL
    precommit: str  # PASS or FAIL
    failure_reasons: List[str]
    
    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


class ValidationAgent:
    """Main validation agent."""
    
    def __init__(self, repo_path: str = ".", github_token: str = None):
        """
        Initialize validation agent.
        
        Args:
            repo_path: Path to repository
            github_token: GitHub API token
        """
        self.repo_path = Path(repo_path).resolve()
        self.github = GitHubClient(token=github_token)
        self.git = GitOperations(repo_path=repo_path)
        self.test_runner = TestRunner(repo_path=repo_path)
        self.original_branch = None
    
    def validate_all_prs(self) -> List[ValidationResult]:
        """
        Validate all open PRs.
        
        Returns:
            List of ValidationResult objects
        """
        print("=" * 80)
        print("🔍 VALIDATION AGENT - Starting PR Validation")
        print("=" * 80)
        print()
        
        # Fetch all open PRs
        print("Fetching open PRs from GitHub...")
        prs = self.github.get_open_prs()
        print(f"Found {len(prs)} open PRs")
        print()
        
        # Save current branch
        self.original_branch = self.git.get_current_branch()
        print(f"Original branch: {self.original_branch}")
        print()
        
        # Fetch all remote branches
        print("Fetching remote branches...")
        self.git.fetch_all()
        print()
        
        # Validate each PR
        results = []
        for i, pr in enumerate(prs, 1):
            print(f"[{i}/{len(prs)}] Validating PR #{pr.number}: {pr.title}")
            print("-" * 80)
            
            try:
                result = self.validate_pr(pr)
                results.append(result)
                
                status_emoji = "✅" if result.status == "PASS" else "❌"
                print(f"{status_emoji} PR #{pr.number}: {result.status}")
                
                if result.failure_reasons:
                    print(f"   Failures: {', '.join(result.failure_reasons)}")
                
            except Exception as e:
                print(f"❌ Error validating PR #{pr.number}: {e}")
                
                # Create failure result
                result = ValidationResult(
                    pr_number=pr.number,
                    title=pr.title,
                    status="FAIL",
                    tests={"passed": 0, "failed": 0, "coverage": 0.0},
                    security={"critical": 0, "high": 0, "medium": 0},
                    conflicts=False,
                    invariants="UNKNOWN",
                    precommit="UNKNOWN",
                    failure_reasons=[f"Validation error: {str(e)}"],
                )
                results.append(result)
            
            print()
        
        # Return to original branch
        print(f"Returning to original branch: {self.original_branch}")
        self.git.checkout(self.original_branch)
        
        print()
        print("=" * 80)
        print("🏁 VALIDATION COMPLETE")
        print("=" * 80)
        
        # Print summary
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        
        print(f"Total PRs: {len(results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print()
        
        return results
    
    def validate_pr(self, pr: PullRequest) -> ValidationResult:
        """
        Validate a single PR.
        
        Args:
            pr: PullRequest object
            
        Returns:
            ValidationResult object
        """
        failure_reasons = []
        
        # Checkout PR branch
        print(f"  → Checking out PR branch: {pr.head_ref}")
        try:
            self.git.checkout_pr(pr.number, f"pr-{pr.number}")
        except Exception as e:
            failure_reasons.append(f"Failed to checkout branch: {e}")
            return self._create_failure_result(pr, failure_reasons)
        
        # Check for merge conflicts
        print("  → Checking for merge conflicts...")
        conflicts = False
        try:
            conflicts = self.git.has_merge_conflicts(pr.base_ref)
            if conflicts:
                failure_reasons.append("Merge conflicts with base branch")
        except Exception as e:
            failure_reasons.append(f"Failed to check conflicts: {e}")
        
        # Run tests
        print("  → Running pytest suite...")
        test_result = {"passed": 0, "failed": 0, "coverage": 0.0}
        try:
            result = self.test_runner.run_tests(
                coverage=True,
                verbose=False,
            )
            
            test_result = {
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "coverage": result.coverage,
            }
            
            if result.failed > 0:
                failure_reasons.append(f"Test failures: {result.failed} tests failed")
            
            print(f"     Tests: {result.passed} passed, {result.failed} failed, {result.coverage}% coverage")
        except Exception as e:
            failure_reasons.append(f"Test execution failed: {e}")
            print(f"     Error: {e}")
        
        # Run security scan
        print("  → Running Bandit security scan...")
        security_result = {"critical": 0, "high": 0, "medium": 0}
        try:
            sec_scan = self.test_runner.run_security_scan()
            security_result = sec_scan.get("severity_counts", security_result)
            
            if security_result["critical"] > 0 or security_result["high"] > 0:
                failure_reasons.append(
                    f"Security issues: {security_result['critical']} critical, "
                    f"{security_result['high']} high"
                )
            
            print(f"     Security: {security_result['critical']} critical, "
                  f"{security_result['high']} high, {security_result['medium']} medium")
        except Exception as e:
            failure_reasons.append(f"Security scan failed: {e}")
            print(f"     Error: {e}")
        
        # Run invariant validation
        print("  → Running invariant validation...")
        invariants_status = "PASS"
        try:
            import subprocess
            result = subprocess.run(
                ["python", "scripts/validate_invariants.py"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode != 0:
                invariants_status = "FAIL"
                failure_reasons.append("Invariant validation failed")
            
            print(f"     Invariants: {invariants_status}")
        except Exception as e:
            invariants_status = "UNKNOWN"
            failure_reasons.append(f"Invariant validation error: {e}")
            print(f"     Error: {e}")
        
        # Check pre-commit hooks
        print("  → Checking pre-commit hooks...")
        precommit_status = "PASS"
        try:
            import subprocess
            result = subprocess.run(
                ["pre-commit", "run", "--all-files"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode != 0:
                precommit_status = "FAIL"
                failure_reasons.append("Pre-commit hooks failed")
            
            print(f"     Pre-commit: {precommit_status}")
        except FileNotFoundError:
            # pre-commit not installed, skip
            precommit_status = "SKIP"
            print("     Pre-commit: SKIP (not installed)")
        except Exception as e:
            precommit_status = "UNKNOWN"
            print(f"     Error: {e}")
        
        # Determine overall status
        status = "PASS" if not failure_reasons else "FAIL"
        
        return ValidationResult(
            pr_number=pr.number,
            title=pr.title,
            status=status,
            tests=test_result,
            security=security_result,
            conflicts=conflicts,
            invariants=invariants_status,
            precommit=precommit_status,
            failure_reasons=failure_reasons,
        )
    
    def _create_failure_result(self, pr: PullRequest, failure_reasons: List[str]) -> ValidationResult:
        """
        Create a failure result for a PR.
        
        Args:
            pr: PullRequest object
            failure_reasons: List of failure reasons
            
        Returns:
            ValidationResult object with FAIL status
        """
        return ValidationResult(
            pr_number=pr.number,
            title=pr.title,
            status="FAIL",
            tests={"passed": 0, "failed": 0, "coverage": 0.0},
            security={"critical": 0, "high": 0, "medium": 0},
            conflicts=False,
            invariants="UNKNOWN",
            precommit="UNKNOWN",
            failure_reasons=failure_reasons,
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validation Agent for PR validation")
    parser.add_argument(
        "--output",
        type=str,
        default="reports/validation_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repository path",
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run validation
    agent = ValidationAgent(repo_path=args.repo)
    results = agent.validate_all_prs()
    
    # Save results
    output_data = {
        "total_prs": len(results),
        "passed": sum(1 for r in results if r.status == "PASS"),
        "failed": sum(1 for r in results if r.status == "FAIL"),
        "results": [r.to_dict() for r in results],
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Results saved to: {output_path}")
    
    # Exit with appropriate code
    sys.exit(0 if output_data["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
