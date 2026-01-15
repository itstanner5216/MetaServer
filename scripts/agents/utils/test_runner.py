#!/usr/bin/env python3
"""Test runner utilities for pytest execution and result parsing."""

import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TestResult:
    """Represents test execution results."""
    
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    total: int = 0
    duration: float = 0.0
    coverage: float = 0.0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


class TestRunner:
    """Pytest execution and result parsing."""
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize test runner.
        
        Args:
            repo_path: Path to repository
        """
        self.repo_path = Path(repo_path).resolve()
    
    def run_tests(
        self,
        test_path: Optional[str] = None,
        markers: Optional[List[str]] = None,
        coverage: bool = True,
        verbose: bool = True,
        json_output: bool = True,
    ) -> TestResult:
        """
        Run pytest tests.
        
        Args:
            test_path: Specific test path (default: tests/)
            markers: Test markers to filter by
            coverage: Enable coverage reporting
            verbose: Enable verbose output
            json_output: Generate JSON report
            
        Returns:
            TestResult object
        """
        # Build pytest command
        cmd = ["pytest"]
        
        # Add test path
        if test_path:
            cmd.append(test_path)
        else:
            cmd.append("tests/")
        
        # Add markers
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])
        
        # Add verbosity
        if verbose:
            cmd.append("-v")
        
        # Add coverage
        if coverage:
            cmd.extend([
                "--cov=src",
                "--cov=MetaServer",
                "--cov-report=term-missing",
                "--cov-report=json",
            ])
        
        # Add JSON report
        if json_output:
            json_path = self.repo_path / "reports" / "pytest_report.json"
            json_path.parent.mkdir(exist_ok=True)
            cmd.append(f"--json-report")
            cmd.append(f"--json-report-file={json_path}")
        
        # Run tests
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        
        # Parse results
        test_result = self._parse_results(result, json_output)
        
        return test_result
    
    def _parse_results(self, process_result: subprocess.CompletedProcess, has_json: bool) -> TestResult:
        """
        Parse pytest results.
        
        Args:
            process_result: Subprocess result
            has_json: Whether JSON report was generated
            
        Returns:
            TestResult object
        """
        test_result = TestResult(
            exit_code=process_result.returncode,
            stdout=process_result.stdout,
            stderr=process_result.stderr,
        )
        
        # Try to parse JSON report if available
        if has_json:
            json_path = self.repo_path / "reports" / "pytest_report.json"
            if json_path.exists():
                try:
                    with open(json_path) as f:
                        data = json.load(f)
                    
                    # Extract test counts
                    summary = data.get("summary", {})
                    test_result.passed = summary.get("passed", 0)
                    test_result.failed = summary.get("failed", 0)
                    test_result.skipped = summary.get("skipped", 0)
                    test_result.error = summary.get("error", 0)
                    test_result.total = summary.get("total", 0)
                    test_result.duration = data.get("duration", 0.0)
                    
                    # Extract failures
                    for test in data.get("tests", []):
                        if test.get("outcome") in ["failed", "error"]:
                            test_result.failures.append({
                                "name": test.get("nodeid", ""),
                                "outcome": test.get("outcome", ""),
                                "message": test.get("call", {}).get("longrepr", ""),
                                "traceback": test.get("call", {}).get("traceback", ""),
                            })
                except Exception as e:
                    print(f"Warning: Failed to parse JSON report: {e}")
        
        # Parse coverage if available
        coverage_path = self.repo_path / "coverage.json"
        if coverage_path.exists():
            try:
                with open(coverage_path) as f:
                    cov_data = json.load(f)
                
                # Calculate coverage percentage
                totals = cov_data.get("totals", {})
                percent_covered = totals.get("percent_covered", 0.0)
                test_result.coverage = round(percent_covered, 2)
            except Exception as e:
                print(f"Warning: Failed to parse coverage report: {e}")
        
        # Fallback: parse from stdout if JSON not available
        if test_result.total == 0:
            self._parse_text_output(test_result)
        
        return test_result
    
    def _parse_text_output(self, test_result: TestResult):
        """
        Parse pytest text output as fallback.
        
        Args:
            test_result: TestResult to update
        """
        lines = test_result.stdout.split("\n")
        
        for line in lines:
            # Look for summary line like: "5 passed, 2 failed in 3.45s"
            if " passed" in line or " failed" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            test_result.passed = int(parts[i - 1])
                        except ValueError:
                            pass
                    elif part == "failed" and i > 0:
                        try:
                            test_result.failed = int(parts[i - 1])
                        except ValueError:
                            pass
                    elif part == "skipped" and i > 0:
                        try:
                            test_result.skipped = int(parts[i - 1])
                        except ValueError:
                            pass
            
            # Look for coverage line like: "TOTAL 1234 567 54%"
            if "TOTAL" in line and "%" in line:
                try:
                    parts = line.split()
                    for part in parts:
                        if "%" in part:
                            test_result.coverage = float(part.rstrip("%"))
                            break
                except ValueError:
                    pass
        
        test_result.total = test_result.passed + test_result.failed + test_result.skipped
    
    def run_security_scan(self, severity: str = "medium") -> Dict[str, Any]:
        """
        Run Bandit security scanner.
        
        Args:
            severity: Minimum severity level (low, medium, high)
            
        Returns:
            Dictionary with security scan results
        """
        cmd = [
            "bandit",
            "-r",
            "src",
            "MetaServer",
            "-f", "json",
            "-ll",  # Low confidence, low severity minimum
            "-o", str(self.repo_path / "reports" / "bandit_report.json"),
        ]
        
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        
        # Parse Bandit results
        report_path = self.repo_path / "reports" / "bandit_report.json"
        if report_path.exists():
            with open(report_path) as f:
                data = json.load(f)
            
            # Count by severity
            severity_counts = {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }
            
            for issue in data.get("results", []):
                sev = issue.get("issue_severity", "").lower()
                if sev in severity_counts:
                    severity_counts[sev] += 1
            
            return {
                "total_issues": len(data.get("results", [])),
                "severity_counts": severity_counts,
                "issues": data.get("results", []),
                "exit_code": result.returncode,
            }
        
        return {
            "total_issues": 0,
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "issues": [],
            "exit_code": result.returncode,
        }
    
    def get_failure_patterns(self, test_result: TestResult) -> List[Dict[str, str]]:
        """
        Extract common failure patterns from test results.
        
        Args:
            test_result: TestResult object
            
        Returns:
            List of failure patterns with suggested fixes
        """
        patterns = []
        
        for failure in test_result.failures:
            message = failure.get("message", "")
            
            # Pattern: ModuleNotFoundError
            if "ModuleNotFoundError" in message or "ImportError" in message:
                patterns.append({
                    "type": "import_error",
                    "test": failure.get("name", ""),
                    "message": message,
                    "suggestion": "Fix import paths or add missing dependencies",
                })
            
            # Pattern: AssertionError
            elif "AssertionError" in message:
                patterns.append({
                    "type": "assertion_error",
                    "test": failure.get("name", ""),
                    "message": message,
                    "suggestion": "Review test expectations and actual behavior",
                })
            
            # Pattern: Fixture errors
            elif "fixture" in message.lower():
                patterns.append({
                    "type": "fixture_error",
                    "test": failure.get("name", ""),
                    "message": message,
                    "suggestion": "Check fixture scope and dependencies",
                })
            
            # Pattern: Timeout
            elif "timeout" in message.lower() or "TimeoutError" in message:
                patterns.append({
                    "type": "timeout",
                    "test": failure.get("name", ""),
                    "message": message,
                    "suggestion": "Increase timeout or optimize test execution",
                })
            
            # Generic failure
            else:
                patterns.append({
                    "type": "unknown",
                    "test": failure.get("name", ""),
                    "message": message,
                    "suggestion": "Manual investigation required",
                })
        
        return patterns
