#!/usr/bin/env python3
"""
CLI runner for AI agent workflow.
Executes individual agents or entire pipeline.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from .llm_config import AgentRole
from .llm_validation_agent import LLMValidationAgent
from .llm_remediation_agent import LLMRemediationAgent
from .llm_architectural_guardian import LLMArchitecturalGuardian
from .llm_functional_verifier import LLMFunctionalVerifier


AGENTS = {
    "validator": LLMValidationAgent,
    "remediator": LLMRemediationAgent,
    "guardian": LLMArchitecturalGuardian,
    "verifier": LLMFunctionalVerifier,
}


async def run_single_agent(
    agent_name: str,
    pr_number: int,
    repo_owner: str = "itstanner5216",
    repo_name: str = "MetaServer",
    dry_run: bool = False,
) -> dict:
    """
    Run a single agent on a PR.
    
    Args:
        agent_name: Name of agent to run (validator, remediator, guardian, verifier)
        pr_number: PR number to analyze
        repo_owner: Repository owner
        repo_name: Repository name
        dry_run: If True, don't post comments
        
    Returns:
        Agent output as dictionary
    """
    if agent_name not in AGENTS:
        raise ValueError(f"Unknown agent: {agent_name}. Choose from: {list(AGENTS.keys())}")
    
    agent_class = AGENTS[agent_name]
    agent = agent_class(
        repo_owner=repo_owner,
        repo_name=repo_name,
        dry_run=dry_run,
    )
    
    output = await agent.run(pr_number)
    return output.to_dict()


async def run_all_agents(
    pr_number: int,
    repo_owner: str = "itstanner5216",
    repo_name: str = "MetaServer",
    dry_run: bool = False,
) -> dict:
    """
    Run all agents on a PR in sequence.
    
    Args:
        pr_number: PR number to analyze
        repo_owner: Repository owner
        repo_name: Repository name
        dry_run: If True, don't post comments
        
    Returns:
        Dictionary with all agent outputs
    """
    results = {}
    
    for agent_name, agent_class in AGENTS.items():
        print(f"\n{'='*80}")
        print(f"Running {agent_name}...")
        print(f"{'='*80}\n")
        
        try:
            agent = agent_class(
                repo_owner=repo_owner,
                repo_name=repo_name,
                dry_run=dry_run,
            )
            
            output = await agent.run(pr_number)
            results[agent_name] = output.to_dict()
            
        except Exception as e:
            print(f"❌ Error running {agent_name}: {e}")
            results[agent_name] = {
                "error": str(e),
                "verdict": "ERROR",
            }
    
    return results


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI Agent Pipeline - Run LLM-based PR analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all agents on PR #123
  python -m scripts.agents.run_agent --pr 123 --all
  
  # Run only the validator agent
  python -m scripts.agents.run_agent --pr 123 --agent validator
  
  # Run in dry-run mode (don't post comments)
  python -m scripts.agents.run_agent --pr 123 --all --dry-run
  
  # Save results to file
  python -m scripts.agents.run_agent --pr 123 --all --output results.json
        """,
    )
    
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number to analyze",
    )
    
    parser.add_argument(
        "--agent",
        type=str,
        choices=list(AGENTS.keys()),
        help="Specific agent to run (validator, remediator, guardian, verifier)",
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all agents in sequence",
    )
    
    parser.add_argument(
        "--repo-owner",
        type=str,
        default="itstanner5216",
        help="Repository owner (default: itstanner5216)",
    )
    
    parser.add_argument(
        "--repo-name",
        type=str,
        default="MetaServer",
        help="Repository name (default: MetaServer)",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't post comments to GitHub (just print them)",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to JSON file",
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.agent and not args.all:
        parser.error("Must specify either --agent or --all")
    
    if args.agent and args.all:
        parser.error("Cannot specify both --agent and --all")
    
    # Run agents
    try:
        if args.all:
            results = asyncio.run(run_all_agents(
                pr_number=args.pr,
                repo_owner=args.repo_owner,
                repo_name=args.repo_name,
                dry_run=args.dry_run,
            ))
        else:
            result = asyncio.run(run_single_agent(
                agent_name=args.agent,
                pr_number=args.pr,
                repo_owner=args.repo_owner,
                repo_name=args.repo_name,
                dry_run=args.dry_run,
            ))
            results = {args.agent: result}
        
        # Print summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")
        
        for agent_name, result in results.items():
            if "error" in result:
                print(f"❌ {agent_name}: ERROR - {result['error']}")
            else:
                verdict = result.get("verdict", "UNKNOWN")
                emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "BLOCK": "🚫"}.get(verdict, "❓")
                print(f"{emoji} {agent_name}: {verdict} - {result.get('summary', 'No summary')}")
        
        # Save to file if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            
            print(f"\n✅ Results saved to: {output_path}")
        
        # Exit with appropriate code
        has_errors = any("error" in r for r in results.values())
        has_blocks = any(r.get("verdict") == "BLOCK" for r in results.values())
        has_fails = any(r.get("verdict") == "FAIL" for r in results.values())
        
        if has_errors or has_blocks:
            sys.exit(2)
        elif has_fails:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
