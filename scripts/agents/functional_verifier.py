#!/usr/bin/env python3
"""
Functional Verification Agent - Verify meta-PRs don't break functionality.

Test suite:
- Integration tests
- Behavioral regression tests
- Performance benchmarking
- Server startup & health checks

Input: reports/meta_prs_created.json
Output: reports/functional_verification.json
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.agents.utils.github_client import GitHubClient
from scripts.agents.utils.git_operations import GitOperations
from scripts.agents.utils.test_runner import TestRunner


@dataclass
class FunctionalVerificationResult:
    """Functional verification result for a meta-PR."""
    
    meta_pr_branch: str
    bundled_prs: List[int]
    functional_verdict: str  # PASS, FAIL
    tests_passed: int
    tests_failed: int
    behavioral_changes_detected: bool
    performance_delta: str
    recommendation: str
    details: Dict[str, Any]
    
    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


class FunctionalVerifier:
    """Functional verification agent."""
    
    def __init__(self, repo_path: str = ".", github_token: str = None):
        """
        Initialize functional verifier.
        
        Args:
            repo_path: Path to repository
            github_token: GitHub API token
        """
        self.repo_path = Path(repo_path).resolve()
        self.github = GitHubClient(token=github_token)
        self.git = GitOperations(repo_path=repo_path)
        self.test_runner = TestRunner(repo_path=repo_path)
        self.original_branch = None
    
    def verify_meta_prs(self, meta_prs: List[Dict[str, Any]]) -> List[FunctionalVerificationResult]:
        """
        Verify functional integrity of meta-PRs.
        
        Args:
            meta_prs: List of meta-PR dictionaries
            
        Returns:
            List of FunctionalVerificationResult objects
        """
        print("=" * 80)
        print("✅ FUNCTIONAL VERIFIER - Verifying Meta-PRs")
        print("=" * 80)
        print()
        
        # Save original branch
        self.original_branch = self.git.get_current_branch()
        
        print(f"Verifying {len(meta_prs)} meta-PRs")
        print()
        
        # Get baseline metrics from main branch
        print("Getting baseline metrics from main branch...")
        self.git.checkout("main")
        baseline = self._get_baseline_metrics()
        print()
        
        # Verify each meta-PR
        results = []
        for i, meta_pr in enumerate(meta_prs, 1):
            branch = meta_pr.get("branch")
            bundled_prs = meta_pr.get("bundled_prs", [])
            
            print(f"[{i}/{len(meta_prs)}] Verifying meta-PR: {branch}")
            print(f"   Bundled PRs: {bundled_prs}")
            print("-" * 80)
            
            try:
                result = self.verify_meta_pr(branch, bundled_prs, baseline)
                results.append(result)
                
                status_emoji = "✅" if result.functional_verdict == "PASS" else "❌"
                print(f"{status_emoji} {branch}: {result.functional_verdict}")
                print(f"   Tests: {result.tests_passed} passed, {result.tests_failed} failed")
                print(f"   Performance: {result.performance_delta}")
                print(f"   Recommendation: {result.recommendation}")
                
            except Exception as e:
                print(f"❌ Error verifying {branch}: {e}")
                
                result = FunctionalVerificationResult(
                    meta_pr_branch=branch,
                    bundled_prs=bundled_prs,
                    functional_verdict="FAIL",
                    tests_passed=0,
                    tests_failed=0,
                    behavioral_changes_detected=False,
                    performance_delta="N/A",
                    recommendation="MANUAL_REVIEW",
                    details={"error": str(e)},
                )
                results.append(result)
            
            print()
        
        # Return to original branch
        print(f"Returning to original branch: {self.original_branch}")
        self.git.checkout(self.original_branch)
        
        print()
        print("=" * 80)
        print("🏁 FUNCTIONAL VERIFICATION COMPLETE")
        print("=" * 80)
        
        # Print summary
        passed = sum(1 for r in results if r.functional_verdict == "PASS")
        failed = sum(1 for r in results if r.functional_verdict == "FAIL")
        
        print(f"Total meta-PRs verified: {len(results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print()
        
        return results
    
    def verify_meta_pr(
        self,
        branch: str,
        bundled_prs: List[int],
        baseline: Dict[str, Any],
    ) -> FunctionalVerificationResult:
        """
        Verify a single meta-PR.
        
        Args:
            branch: Meta-PR branch name
            bundled_prs: List of bundled PR numbers
            baseline: Baseline metrics
            
        Returns:
            FunctionalVerificationResult object
        """
        # Checkout meta-PR branch
        print(f"  → Checking out meta-PR branch: {branch}")
        self.git.checkout(branch)
        
        details = {}
        
        # Run integration tests
        print(f"  → Running integration tests...")
        test_result = self._run_integration_tests()
        details["integration_tests"] = test_result
        
        # Run behavioral regression tests
        print(f"  → Running behavioral regression tests...")
        behavioral_changes = self._check_behavioral_regressions(baseline)
        details["behavioral_changes"] = behavioral_changes
        
        # Run performance benchmarks
        print(f"  → Running performance benchmarks...")
        performance = self._run_performance_benchmarks(baseline)
        details["performance"] = performance
        
        # Check server health
        print(f"  → Checking server health...")
        server_health = self._check_server_health()
        details["server_health"] = server_health
        
        # Determine verdict
        tests_passed = test_result.get("passed", 0)
        tests_failed = test_result.get("failed", 0)
        
        functional_verdict = "PASS"
        if tests_failed > 0:
            functional_verdict = "FAIL"
        if not server_health.get("healthy", False):
            functional_verdict = "FAIL"
        if performance.get("degradation_percent", 0) > 10:
            functional_verdict = "FAIL"
        
        # Determine recommendation
        recommendation = "READY_TO_MERGE"
        if functional_verdict == "FAIL":
            recommendation = "DO_NOT_MERGE"
        elif behavioral_changes or performance.get("degradation_percent", 0) > 5:
            recommendation = "REVIEW_REQUIRED"
        
        return FunctionalVerificationResult(
            meta_pr_branch=branch,
            bundled_prs=bundled_prs,
            functional_verdict=functional_verdict,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            behavioral_changes_detected=bool(behavioral_changes),
            performance_delta=f"{performance.get('delta_percent', 0):+.1f}%",
            recommendation=recommendation,
            details=details,
        )
    
    def _get_baseline_metrics(self) -> Dict[str, Any]:
        """Get baseline metrics from current branch."""
        baseline = {}
        
        # Run tests
        try:
            test_result = self.test_runner.run_tests(
                test_path="tests/integration/",
                coverage=False,
                verbose=False,
            )
            baseline["tests"] = {
                "passed": test_result.passed,
                "failed": test_result.failed,
                "total": test_result.total,
            }
        except Exception:
            baseline["tests"] = {"passed": 0, "failed": 0, "total": 0}
        
        # Simple performance metric (test execution time)
        baseline["performance"] = {
            "test_duration": baseline.get("tests", {}).get("duration", 0),
        }
        
        return baseline
    
    def _run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests."""
        try:
            result = self.test_runner.run_tests(
                test_path="tests/integration/",
                markers=["integration"],
                coverage=True,
                verbose=False,
            )
            
            return {
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "coverage": result.coverage,
                "duration": result.duration,
            }
        except Exception as e:
            return {
                "passed": 0,
                "failed": 1,
                "skipped": 0,
                "coverage": 0.0,
                "error": str(e),
            }
    
    def _check_behavioral_regressions(self, baseline: Dict[str, Any]) -> List[str]:
        """Check for behavioral regressions."""
        regressions = []
        
        # Compare test counts
        baseline_tests = baseline.get("tests", {})
        current_result = self._run_integration_tests()
        
        if current_result["passed"] < baseline_tests.get("passed", 0):
            regressions.append(
                f"Test regression: {baseline_tests['passed']} -> {current_result['passed']} tests passing"
            )
        
        return regressions
    
    def _run_performance_benchmarks(self, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Run performance benchmarks."""
        # Simple benchmark: compare test execution time
        current = self._run_integration_tests()
        
        baseline_duration = baseline.get("performance", {}).get("test_duration", 1.0)
        current_duration = current.get("duration", 1.0)
        
        if baseline_duration > 0:
            delta_percent = ((current_duration - baseline_duration) / baseline_duration) * 100
        else:
            delta_percent = 0.0
        
        degradation = max(0, delta_percent)
        
        return {
            "baseline_duration": baseline_duration,
            "current_duration": current_duration,
            "delta_percent": delta_percent,
            "degradation_percent": degradation,
        }
    
    def _check_server_health(self) -> Dict[str, Any]:
        """Check server health."""
        health = {
            "healthy": True,
            "checks": [],
        }
        
        # Check 1: Can import main modules
        try:
            subprocess.run(
                ["python", "-c", "import meta_mcp; import MetaServer"],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                timeout=10,
            )
            health["checks"].append({"name": "Module imports", "status": "PASS"})
        except Exception as e:
            health["healthy"] = False
            health["checks"].append({"name": "Module imports", "status": "FAIL", "error": str(e)})
        
        # Check 2: Validate invariants
        try:
            result = subprocess.run(
                ["python", "scripts/validate_invariants.py"],
                cwd=self.repo_path,
                capture_output=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                health["checks"].append({"name": "Invariants", "status": "PASS"})
            else:
                health["healthy"] = False
                health["checks"].append({"name": "Invariants", "status": "FAIL"})
        except Exception as e:
            health["healthy"] = False
            health["checks"].append({"name": "Invariants", "status": "ERROR", "error": str(e)})
        
        return health


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Functional Verifier for meta-PR verification"
    )
    parser.add_argument(
        "--meta-prs",
        type=str,
        required=True,
        help="Input meta-PRs JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/functional_verification.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repository path",
    )
    
    args = parser.parse_args()
    
    # Load meta-PRs
    with open(args.meta_prs) as f:
        meta_prs_data = json.load(f)
    
    meta_prs = meta_prs_data.get("meta_prs", [])
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run verification
    agent = FunctionalVerifier(repo_path=args.repo)
    results = agent.verify_meta_prs(meta_prs)
    
    # Save results
    output_data = {
        "total_verified": len(results),
        "passed": sum(1 for r in results if r.functional_verdict == "PASS"),
        "failed": sum(1 for r in results if r.functional_verdict == "FAIL"),
        "ready_to_merge": sum(1 for r in results if r.recommendation == "READY_TO_MERGE"),
        "results": [r.to_dict() for r in results],
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Results saved to: {output_path}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
