#!/usr/bin/env python3
"""
Check implementation status of MetaMCP+ phases.

Verifies which phases are complete by checking for:
1. Required files exist
2. Tests exist and pass
3. Integration points are implemented

Usage:
    python scripts/check_phase_status.py [--verbose]
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict
import argparse

# Phase requirements
PHASES = {
    0: {
        "name": "Config",
        "files": [
            "src/meta_mcp/config.py",
        ],
        "tests": ["tests/test_config.py"],
        "risk": "LOW",
    },
    1: {
        "name": "Tool Registry",
        "files": [
            "src/meta_mcp/registry/__init__.py",
            "src/meta_mcp/registry/models.py",
            "src/meta_mcp/registry/registry.py",
            "config/tools.yaml",
        ],
        "tests": ["tests/test_registry.py", "tests/test_registry_models.py"],
        "risk": "LOW",
    },
    2: {
        "name": "Semantic Retrieval",
        "files": [
            "src/meta_mcp/retrieval/__init__.py",
            "src/meta_mcp/retrieval/embedder.py",
            "src/meta_mcp/retrieval/search.py",
        ],
        "tests": ["tests/test_embedder.py", "tests/test_semantic_search.py"],
        "risk": "MEDIUM",
    },
    3: {
        "name": "Lease Manager",
        "files": [
            "src/meta_mcp/leases/__init__.py",
            "src/meta_mcp/leases/models.py",
            "src/meta_mcp/leases/manager.py",
        ],
        "tests": ["tests/test_lease_security.py"],  # Critical test
        "risk": "HIGH",
    },
    4: {
        "name": "Governance Engine",
        "files": [
            "src/meta_mcp/governance/__init__.py",
            "src/meta_mcp/governance/tokens.py",
            "src/meta_mcp/governance/policy.py",
        ],
        "tests": ["tests/test_token_security.py", "tests/test_schema_leakage.py"],
        "risk": "CRITICAL",
    },
    5: {
        "name": "Progressive Schemas",
        "files": [
            "src/meta_mcp/schemas/__init__.py",
            "src/meta_mcp/schemas/minimizer.py",
            "src/meta_mcp/schemas/expander.py",
        ],
        "tests": ["tests/test_schema_minimizer.py"],
        "risk": "MEDIUM",
    },
    6: {
        "name": "TOON Encoding",
        "files": [
            "src/meta_mcp/toon/__init__.py",
            "src/meta_mcp/toon/encoder.py",
        ],
        "tests": ["tests/test_toon_encoder.py"],
        "risk": "LOW",
    },
    7: {
        "name": "Macro Tools",
        "files": [
            "src/meta_mcp/macros/__init__.py",
            "src/meta_mcp/macros/batch_read.py",
        ],
        "tests": ["tests/test_batch_read.py"],
        "risk": "MEDIUM",
    },
    8: {
        "name": "Client Notifications",
        "files": [],  # Just modifications
        "tests": ["tests/test_list_changed_emission.py"],
        "risk": "LOW",
    },
    9: {
        "name": "Benchmarking",
        "files": [
            "scripts/benchmark_baseline.py",
            "scripts/benchmark_optimized.py",
            "scripts/validate_invariants.py",
        ],
        "tests": [],
        "risk": "LOW",
    },
}


def check_files_exist(phase: int) -> Tuple[bool, List[str]]:
    """Check if all required files for a phase exist."""
    missing = []
    for file in PHASES[phase]["files"]:
        if not Path(file).exists():
            missing.append(file)
    return len(missing) == 0, missing


def check_tests_exist(phase: int) -> Tuple[bool, List[str]]:
    """Check if test files exist."""
    missing = []
    for test in PHASES[phase]["tests"]:
        if not Path(test).exists():
            missing.append(test)
    return len(missing) == 0, missing


def run_tests(phase: int, verbose: bool = False) -> Tuple[bool, str]:
    """Run tests for a phase."""
    tests = PHASES[phase]["tests"]

    if not tests:
        return True, "No tests required"

    try:
        cmd = ["pytest"] + tests + ["-v" if verbose else "-q"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return True, "All tests passed"
        elif result.returncode == 5:
            # pytest exit code 5 = no tests collected (all skipped)
            return None, "Tests exist but skipped (not implemented)"
        else:
            return False, f"Tests failed (exit code {result.returncode})"

    except subprocess.TimeoutExpired:
        return False, "Tests timed out"
    except Exception as e:
        return False, f"Test error: {e}"


def get_phase_status(phase: int, verbose: bool = False) -> Dict:
    """Get complete status for a phase."""
    files_ok, missing_files = check_files_exist(phase)
    tests_ok, missing_tests = check_tests_exist(phase)

    status = {
        "phase": phase,
        "name": PHASES[phase]["name"],
        "risk": PHASES[phase]["risk"],
        "files_exist": files_ok,
        "missing_files": missing_files,
        "tests_exist": tests_ok,
        "missing_tests": missing_tests,
        "tests_pass": None,
        "test_message": "",
    }

    # Only run tests if files and tests exist
    if files_ok and tests_ok:
        tests_pass, test_message = run_tests(phase, verbose)
        status["tests_pass"] = tests_pass
        status["test_message"] = test_message

    # Determine overall status
    if files_ok and tests_ok and status["tests_pass"] == True:
        status["overall"] = "COMPLETE"
    elif files_ok and tests_ok and status["tests_pass"] is None:
        status["overall"] = "IMPLEMENTED (tests skipped)"
    elif files_ok and not tests_ok:
        status["overall"] = "FILES ONLY (no tests)"
    elif not files_ok:
        status["overall"] = "NOT STARTED"
    else:
        status["overall"] = "PARTIAL"

    return status


def print_status(status: Dict, verbose: bool = False):
    """Print phase status."""
    phase = status["phase"]
    name = status["name"]
    overall = status["overall"]
    risk = status["risk"]

    # Color coding
    if overall == "COMPLETE":
        color = "\033[0;32m"  # Green
        symbol = "✅"
    elif overall == "IMPLEMENTED (tests skipped)":
        color = "\033[1;33m"  # Yellow
        symbol = "⚠️"
    elif overall == "NOT STARTED":
        color = "\033[0;37m"  # Gray
        symbol = "⬜"
    else:
        color = "\033[0;33m"  # Orange
        symbol = "🟡"

    reset = "\033[0m"

    # Risk color
    risk_colors = {
        "LOW": "\033[0;32m",
        "MEDIUM": "\033[1;33m",
        "HIGH": "\033[0;31m",
        "CRITICAL": "\033[1;31m",
    }
    risk_color = risk_colors.get(risk, "")

    print(f"{symbol} Phase {phase}: {name} - {color}{overall}{reset} [{risk_color}{risk}{reset}]")

    if verbose:
        if status["missing_files"]:
            print(f"  Missing files: {', '.join(status['missing_files'])}")
        if status["missing_tests"]:
            print(f"  Missing tests: {', '.join(status['missing_tests'])}")
        if status["test_message"]:
            print(f"  Test status: {status['test_message']}")


def main():
    parser = argparse.ArgumentParser(description="Check MetaMCP+ phase status")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--phase", "-p", type=int, help="Check specific phase only")
    args = parser.parse_args()

    print("MetaMCP+ Implementation Status")
    print("=" * 50)
    print()

    if args.phase is not None:
        phases_to_check = [args.phase]
    else:
        phases_to_check = range(10)

    statuses = []
    for phase in phases_to_check:
        status = get_phase_status(phase, args.verbose)
        statuses.append(status)
        print_status(status, args.verbose)

    # Summary
    if not args.phase:
        print()
        print("=" * 50)
        complete = sum(1 for s in statuses if s["overall"] == "COMPLETE")
        partial = sum(1 for s in statuses if "PARTIAL" in s["overall"] or "FILES ONLY" in s["overall"])
        not_started = sum(1 for s in statuses if s["overall"] == "NOT STARTED")

        print(f"Summary: {complete}/10 complete, {partial} partial, {not_started} not started")

        # Next steps
        next_phase = None
        for status in statuses:
            if status["overall"] == "NOT STARTED":
                next_phase = status["phase"]
                break

        if next_phase is not None:
            print(f"\nNext phase to implement: Phase {next_phase} ({PHASES[next_phase]['name']})")
            print(f"Risk level: {PHASES[next_phase]['risk']}")
        else:
            print("\n✅ All phases complete!")


if __name__ == "__main__":
    main()
