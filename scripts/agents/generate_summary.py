#!/usr/bin/env python3
"""
Summary Generator - Aggregate all agent reports into final summary.

Inputs:
- reports/validation_results.json
- reports/remediation_results.json
- reports/architectural_analysis.json
- reports/meta_prs_created.json
- reports/functional_verification.json

Output: reports/FINAL_SUMMARY.md
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class SummaryGenerator:
    """Generate final summary report."""
    
    def __init__(self, reports_dir: str = "reports"):
        """
        Initialize summary generator.
        
        Args:
            reports_dir: Directory containing report files
        """
        self.reports_dir = Path(reports_dir)
        self.reports = {}
    
    def load_reports(self):
        """Load all report files."""
        report_files = {
            "validation": "validation_results.json",
            "remediation": "remediation_results.json",
            "architectural": "architectural_analysis.json",
            "meta_prs": "meta_prs_created.json",
            "functional": "functional_verification.json",
        }
        
        for key, filename in report_files.items():
            file_path = self.reports_dir / filename
            
            if file_path.exists():
                with open(file_path) as f:
                    self.reports[key] = json.load(f)
            else:
                print(f"Warning: {filename} not found")
                self.reports[key] = {}
    
    def generate_summary(self) -> str:
        """
        Generate summary markdown.
        
        Returns:
            Summary markdown string
        """
        self.load_reports()
        
        summary = self._generate_header()
        summary += self._generate_validation_summary()
        summary += self._generate_remediation_summary()
        summary += self._generate_architectural_summary()
        summary += self._generate_meta_pr_summary()
        summary += self._generate_functional_summary()
        summary += self._generate_action_items()
        summary += self._generate_footer()
        
        return summary
    
    def _generate_header(self) -> str:
        """Generate report header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f"""# 🤖 AI Agent System - Final Summary Report

**Generated:** {timestamp}

---

## Executive Summary

The MetaServer PR Validation & Auto-Remediation system has completed its analysis of all open pull requests.

"""
    
    def _generate_validation_summary(self) -> str:
        """Generate validation summary section."""
        validation = self.reports.get("validation", {})
        
        if not validation:
            return "## 🔍 Validation Results\n\n*No validation results available*\n\n"
        
        total = validation.get("total_prs", 0)
        passed = validation.get("passed", 0)
        failed = validation.get("failed", 0)
        
        summary = f"""## 🔍 Validation Results

**Total PRs Validated:** {total}
- ✅ Passed: {passed}
- ❌ Failed: {failed}
- 📊 Pass Rate: {(passed/total*100) if total > 0 else 0:.1f}%

### Validation Breakdown

"""
        
        # Categorize failures
        failure_categories = {
            "test_failures": 0,
            "security_issues": 0,
            "merge_conflicts": 0,
            "invariant_failures": 0,
        }
        
        for result in validation.get("results", []):
            if result["status"] == "FAIL":
                for reason in result.get("failure_reasons", []):
                    if "test" in reason.lower():
                        failure_categories["test_failures"] += 1
                    if "security" in reason.lower():
                        failure_categories["security_issues"] += 1
                    if "conflict" in reason.lower():
                        failure_categories["merge_conflicts"] += 1
                    if "invariant" in reason.lower():
                        failure_categories["invariant_failures"] += 1
        
        summary += f"""| Category | Count |
|----------|-------|
| Test Failures | {failure_categories['test_failures']} |
| Security Issues | {failure_categories['security_issues']} |
| Merge Conflicts | {failure_categories['merge_conflicts']} |
| Invariant Failures | {failure_categories['invariant_failures']} |

"""
        
        return summary
    
    def _generate_remediation_summary(self) -> str:
        """Generate remediation summary section."""
        remediation = self.reports.get("remediation", {})
        
        if not remediation:
            return "## 🔧 Remediation Results\n\n*No remediation results available*\n\n"
        
        total = remediation.get("total_remediated", 0)
        successful = remediation.get("successful", 0)
        partial = remediation.get("partial", 0)
        failed = remediation.get("failed", 0)
        
        summary = f"""## 🔧 Remediation Results

**Total PRs Remediated:** {total}
- ✅ Successful: {successful}
- ⚠️  Partial: {partial}
- ❌ Failed: {failed}
- 📊 Success Rate: {(successful/total*100) if total > 0 else 0:.1f}%

### Common Fixes Applied

"""
        
        # Count fix types
        fix_types = {}
        for result in remediation.get("results", []):
            for fix in result.get("fixes_applied", []):
                fix_type = fix.split(":")[0] if ":" in fix else fix
                fix_types[fix_type] = fix_types.get(fix_type, 0) + 1
        
        if fix_types:
            for fix_type, count in sorted(fix_types.items(), key=lambda x: -x[1])[:10]:
                summary += f"- {fix_type}: {count}\n"
        else:
            summary += "*No fixes applied*\n"
        
        summary += "\n"
        
        return summary
    
    def _generate_architectural_summary(self) -> str:
        """Generate architectural analysis summary section."""
        architectural = self.reports.get("architectural", {})
        
        if not architectural:
            return "## 🏛️  Architectural Analysis\n\n*No architectural analysis available*\n\n"
        
        total = architectural.get("total_analyzed", 0)
        safe = architectural.get("safe", 0)
        review = architectural.get("review", 0)
        reject = architectural.get("reject", 0)
        
        summary = f"""## 🏛️  Architectural Analysis

**Total PRs Analyzed:** {total}
- ✅ Safe: {safe}
- ⚠️  Review: {review}
- ❌ Reject: {reject}
- 📊 Safe Rate: {(safe/total*100) if total > 0 else 0:.1f}%

### Change Classification

"""
        
        # Count classifications
        classifications = {}
        for verdict in architectural.get("verdicts", []):
            classification = verdict.get("change_classification", "unknown")
            classifications[classification] = classifications.get(classification, 0) + 1
        
        if classifications:
            for classification, count in sorted(classifications.items(), key=lambda x: -x[1]):
                summary += f"- {classification.replace('_', ' ').title()}: {count}\n"
        
        summary += "\n### Breaking Changes Detected\n\n"
        
        breaking_count = sum(
            len(v.get("breaking_changes", []))
            for v in architectural.get("verdicts", [])
        )
        
        summary += f"**Total Breaking Changes:** {breaking_count}\n\n"
        
        if breaking_count > 0:
            summary += "⚠️  **Warning:** Breaking changes detected in some PRs. These should not be merged.\n\n"
        
        return summary
    
    def _generate_meta_pr_summary(self) -> str:
        """Generate meta-PR creation summary section."""
        meta_prs = self.reports.get("meta_prs", {})
        
        if not meta_prs:
            return "## 📦 Meta-PRs Created\n\n*No meta-PRs created*\n\n"
        
        total_created = meta_prs.get("total_created", 0)
        total_attempted = meta_prs.get("total_attempted", 0)
        
        summary = f"""## 📦 Meta-PRs Created

**Total Meta-PRs Created:** {total_created}/{total_attempted}

### Meta-PR Breakdown

"""
        
        for meta_pr in meta_prs.get("meta_prs", []):
            title = meta_pr.get("title", "Unknown")
            branch = meta_pr.get("branch", "unknown")
            bundled = len(meta_pr.get("bundled_prs", []))
            created = meta_pr.get("created", False)
            pr_number = meta_pr.get("pr_number", 0)
            
            status = "✅" if created else "❌"
            
            summary += f"{status} **{title}**\n"
            summary += f"   - Branch: `{branch}`\n"
            summary += f"   - Bundled PRs: {bundled}\n"
            
            if pr_number:
                summary += f"   - PR Number: #{pr_number}\n"
            
            if meta_pr.get("error"):
                summary += f"   - Error: {meta_pr['error']}\n"
            
            summary += "\n"
        
        return summary
    
    def _generate_functional_summary(self) -> str:
        """Generate functional verification summary section."""
        functional = self.reports.get("functional", {})
        
        if not functional:
            return "## ✅ Functional Verification\n\n*No functional verification results available*\n\n"
        
        total = functional.get("total_verified", 0)
        passed = functional.get("passed", 0)
        failed = functional.get("failed", 0)
        ready = functional.get("ready_to_merge", 0)
        
        summary = f"""## ✅ Functional Verification

**Total Meta-PRs Verified:** {total}
- ✅ Passed: {passed}
- ❌ Failed: {failed}
- 🚀 Ready to Merge: {ready}

### Verification Details

"""
        
        for result in functional.get("results", []):
            branch = result.get("meta_pr_branch", "unknown")
            verdict = result.get("functional_verdict", "UNKNOWN")
            tests_passed = result.get("tests_passed", 0)
            tests_failed = result.get("tests_failed", 0)
            perf_delta = result.get("performance_delta", "N/A")
            recommendation = result.get("recommendation", "UNKNOWN")
            
            status = "✅" if verdict == "PASS" else "❌"
            
            summary += f"{status} **{branch}**\n"
            summary += f"   - Tests: {tests_passed} passed, {tests_failed} failed\n"
            summary += f"   - Performance: {perf_delta}\n"
            summary += f"   - Recommendation: {recommendation}\n"
            summary += "\n"
        
        return summary
    
    def _generate_action_items(self) -> str:
        """Generate action items section."""
        summary = """## 📋 Action Items

### Ready to Merge

"""
        
        # Get ready-to-merge meta-PRs
        functional = self.reports.get("functional", {})
        ready_meta_prs = [
            r for r in functional.get("results", [])
            if r.get("recommendation") == "READY_TO_MERGE"
        ]
        
        if ready_meta_prs:
            for meta_pr in ready_meta_prs:
                branch = meta_pr.get("meta_pr_branch", "unknown")
                bundled = meta_pr.get("bundled_prs", [])
                summary += f"- [ ] Merge meta-PR: `{branch}` (bundles {len(bundled)} PRs)\n"
        else:
            summary += "*No meta-PRs ready to merge*\n"
        
        summary += "\n### Requires Manual Review\n\n"
        
        # Get PRs requiring review
        architectural = self.reports.get("architectural", {})
        review_prs = [
            v for v in architectural.get("verdicts", [])
            if v.get("recommendation") == "MANUAL_REVIEW"
        ]
        
        if review_prs:
            for pr in review_prs[:10]:  # Limit to 10
                pr_number = pr.get("pr_number", 0)
                title = pr.get("title", "Unknown")
                summary += f"- [ ] Review PR #{pr_number}: {title}\n"
        else:
            summary += "*No PRs require manual review*\n"
        
        summary += "\n### Failed PRs (Require Fixes)\n\n"
        
        # Get failed PRs
        validation = self.reports.get("validation", {})
        failed_prs = [
            r for r in validation.get("results", [])
            if r.get("status") == "FAIL"
        ]
        
        if failed_prs:
            for pr in failed_prs[:10]:  # Limit to 10
                pr_number = pr.get("pr_number", 0)
                title = pr.get("title", "Unknown")
                reasons = ", ".join(pr.get("failure_reasons", [])[:2])
                summary += f"- [ ] Fix PR #{pr_number}: {title} ({reasons})\n"
        else:
            summary += "*No failed PRs*\n"
        
        summary += "\n"
        
        return summary
    
    def _generate_footer(self) -> str:
        """Generate report footer."""
        return """---

## 🔒 Safety Notes

- All meta-PRs are created as **draft PRs** for manual review
- Rollback instructions are included in each meta-PR description
- Breaking changes are automatically rejected
- Manual review is recommended for behavioral changes

## 📊 System Statistics

"""


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate final summary report"
    )
    parser.add_argument(
        "--reports-dir",
        type=str,
        default="reports",
        help="Directory containing report files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/FINAL_SUMMARY.md",
        help="Output markdown file path",
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate summary
    generator = SummaryGenerator(reports_dir=args.reports_dir)
    summary = generator.generate_summary()
    
    # Save summary
    with open(output_path, "w") as f:
        f.write(summary)
    
    print(f"Summary saved to: {output_path}")
    print()
    print("=" * 80)
    print(summary)
    print("=" * 80)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
