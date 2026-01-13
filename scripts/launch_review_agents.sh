#!/bin/bash
#
# Launch 4 parallel review agents for comprehensive code review
#
# Usage: ./scripts/launch_review_agents.sh
#

set -e

REPORTS_DIR="reports"
mkdir -p "$REPORTS_DIR"

echo "================================================"
echo "MetaMCP+ Multi-Model Code Review"
echo "================================================"
echo ""
echo "Launching 4 review agents in parallel..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Agent prompts
AGENT_1_PROMPT="You are Agent 1: Architecture & Design Review.

Review the MetaMCP+ codebase for architectural integrity and design patterns.

Tasks:
1. Review all files in src/meta_mcp/ for architecture compliance
2. Check phase integration (0-9) follows design plan in .MCP/IMPLEMENTATION_HANDOFF.md
3. Verify data model consistency across phases
4. Check API design patterns are consistent
5. Validate module boundaries

Auto-fix:
- Missing type hints
- Inconsistent naming
- Missing docstrings for public APIs

Report to: reports/architecture_review.json

Include:
- files_reviewed count
- issues by severity (critical/high/medium/low)
- auto_fixes applied
- recommendations

Focus on big architectural issues, not style."

AGENT_2_PROMPT="You are Agent 2: Security & Governance Review.

Review the MetaMCP+ codebase for security vulnerabilities and governance issues.

Tasks:
1. Audit all authentication/authorization code
2. Check lease isolation (client_id scoping) in src/meta_mcp/leases/
3. Validate HMAC token security in src/meta_mcp/governance/tokens.py
4. Check for SQL injection, XSS, path traversal
5. Verify policy matrix enforcement in src/meta_mcp/governance/policy.py
6. Check Redis key isolation prevents cross-client access
7. Validate input sanitization everywhere

Auto-fix:
- Missing client_id validation
- Weak validation patterns
- Unsafe error messages

Report to: reports/security_review.json

CRITICAL priority: Any vulnerability that allows:
- Authorization bypass
- Token forgery
- Cross-client data access
- Privilege escalation

Include specific CVE-style descriptions for critical issues."

AGENT_3_PROMPT="You are Agent 3: Code Quality & Patterns Review.

Review the MetaMCP+ codebase for code quality and maintainability.

Tasks:
1. Check error handling consistency (fail-closed pattern)
2. Review logging sufficiency
3. Validate async/await patterns
4. Check resource cleanup (Redis connections)
5. Identify race conditions
6. Find code duplication
7. Review test coverage in tests/

Auto-fix:
- Missing type hints
- Inconsistent error handling
- Magic numbers → constants
- Unused imports
- Simple code duplication

Report to: reports/code_quality_review.json

Focus on maintainability and testing gaps."

AGENT_4_PROMPT="You are Agent 4: Performance & Scalability Review.

Review the MetaMCP+ codebase for performance issues.

Tasks:
1. Check algorithm complexity (look for O(n²))
2. Review caching in src/meta_mcp/retrieval/embedder.py
3. Check Redis operation batching
4. Find N+1 query patterns
5. Review memory usage (unclosed connections)
6. Check concurrency opportunities
7. Review benchmark results in benchmarks/ if available

Auto-fix:
- Add caching to hot paths
- Batch Redis operations
- Simple O(n²) → O(n) optimizations

Report to: reports/performance_review.json

Include specific metrics where possible (estimated improvement %)."

echo "${YELLOW}[1/4]${NC} Launching Architecture Review Agent..."
echo "$AGENT_1_PROMPT" > /tmp/agent1_prompt.txt

echo "${YELLOW}[2/4]${NC} Launching Security Review Agent..."
echo "$AGENT_2_PROMPT" > /tmp/agent2_prompt.txt

echo "${YELLOW}[3/4]${NC} Launching Code Quality Review Agent..."
echo "$AGENT_3_PROMPT" > /tmp/agent3_prompt.txt

echo "${YELLOW}[4/4]${NC} Launching Performance Review Agent..."
echo "$AGENT_4_PROMPT" > /tmp/agent4_prompt.txt

echo ""
echo "${GREEN}✓${NC} All 4 agents are running in background"
echo ""
echo "Monitor progress in reports/ directory:"
echo "  - reports/architecture_review.json"
echo "  - reports/security_review.json"
echo "  - reports/code_quality_review.json"
echo "  - reports/performance_review.json"
echo ""
echo "After all agents complete, run:"
echo "  ./scripts/consolidate_reviews.sh"
echo ""
echo "Estimated completion: 20-30 minutes"
echo ""

# Note: Actual agent launching would happen here
# This script is a template - actual execution via Claude Code Task API
echo "${YELLOW}NOTE:${NC} This script template shows the workflow."
echo "Actual execution: Use Claude Code to launch these as parallel Task agents."
