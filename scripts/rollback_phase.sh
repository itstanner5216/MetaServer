#!/bin/bash
# Rollback script for MetaMCP+ phase implementation
#
# Usage:
#   ./scripts/rollback_phase.sh <phase_number> [--confirm]
#
# Example:
#   ./scripts/rollback_phase.sh 3 --confirm
#
# This script safely rolls back a phase by:
# 1. Verifying git status (must be in git repo)
# 2. Removing files created in that phase
# 3. Restoring modified files from git
# 4. Running regression tests to verify stability

set -e  # Exit on error

PHASE=$1
CONFIRM=$2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Phase file mappings
declare -A PHASE_FILES

# Phase 0: Config
PHASE_FILES[0]="
src/meta_mcp/config.py
"

# Phase 1: Registry
PHASE_FILES[1]="
src/meta_mcp/registry/__init__.py
src/meta_mcp/registry/models.py
src/meta_mcp/registry/registry.py
config/tools.yaml
tests/test_registry.py
tests/test_registry_models.py
"

# Phase 2: Semantic Retrieval
PHASE_FILES[2]="
src/meta_mcp/retrieval/__init__.py
src/meta_mcp/retrieval/embedder.py
src/meta_mcp/retrieval/search.py
tests/test_embedder.py
tests/test_semantic_search.py
tests/test_retrieval_performance.py
"

# Phase 3: Lease Manager
PHASE_FILES[3]="
src/meta_mcp/leases/__init__.py
src/meta_mcp/leases/models.py
src/meta_mcp/leases/manager.py
tests/test_lease_models.py
tests/test_lease_manager.py
tests/test_lease_security.py
tests/test_lease_integration.py
"

# Phase 4: Governance Engine
PHASE_FILES[4]="
src/meta_mcp/governance/__init__.py
src/meta_mcp/governance/tokens.py
src/meta_mcp/governance/policy.py
tests/test_capability_tokens.py
tests/test_token_security.py
tests/test_policy_engine.py
tests/test_governance_integration.py
tests/test_schema_leakage.py
"

# Phase 5: Progressive Schemas
PHASE_FILES[5]="
src/meta_mcp/schemas/__init__.py
src/meta_mcp/schemas/minimizer.py
src/meta_mcp/schemas/expander.py
tests/test_schema_minimizer.py
tests/test_schema_expander.py
tests/test_expand_schema_tool.py
"

# Phase 6: TOON Encoding
PHASE_FILES[6]="
src/meta_mcp/toon/__init__.py
src/meta_mcp/toon/encoder.py
tests/test_toon_encoder.py
tests/test_toon_threshold.py
"

# Phase 7: Macro Tools
PHASE_FILES[7]="
src/meta_mcp/macros/__init__.py
src/meta_mcp/macros/batch_read.py
src/meta_mcp/macros/batch_write.py
src/meta_mcp/macros/batch_search.py
tests/test_batch_read.py
tests/test_batch_write.py
tests/test_batch_search.py
tests/test_macro_governance.py
"

# Phase 8: Client Notifications
PHASE_FILES[8]=""  # No new files, just modifications

# Phase 9: Benchmarking
PHASE_FILES[9]="
scripts/benchmark_baseline.py
scripts/benchmark_optimized.py
scripts/validate_invariants.py
"

# Modified files per phase (need git restore)
declare -A PHASE_MODIFIED

PHASE_MODIFIED[0]="
src/meta_mcp/supervisor.py
src/meta_mcp/state.py
src/meta_mcp/middleware.py
"

PHASE_MODIFIED[1]="
src/meta_mcp/supervisor.py
"

PHASE_MODIFIED[2]="
src/meta_mcp/supervisor.py
src/meta_mcp/registry/registry.py
"

PHASE_MODIFIED[3]="
src/meta_mcp/supervisor.py
src/meta_mcp/middleware.py
src/meta_mcp/state.py
"

PHASE_MODIFIED[4]="
src/meta_mcp/supervisor.py
src/meta_mcp/middleware.py
src/meta_mcp/audit.py
"

PHASE_MODIFIED[5]="
src/meta_mcp/registry/models.py
src/meta_mcp/supervisor.py
config/tools.yaml
"

PHASE_MODIFIED[6]="
src/meta_mcp/middleware.py
src/meta_mcp/config.py
"

PHASE_MODIFIED[7]="
src/meta_mcp/supervisor.py
config/tools.yaml
"

PHASE_MODIFIED[8]="
src/meta_mcp/leases/manager.py
"

PHASE_MODIFIED[9]="
src/meta_mcp/config.py
"

function show_usage() {
    echo "Usage: $0 <phase_number> [--confirm]"
    echo ""
    echo "Phases:"
    echo "  0 - Config"
    echo "  1 - Tool Registry"
    echo "  2 - Semantic Retrieval"
    echo "  3 - Lease Manager"
    echo "  4 - Governance Engine"
    echo "  5 - Progressive Schemas"
    echo "  6 - TOON Encoding"
    echo "  7 - Macro Tools"
    echo "  8 - Client Notifications"
    echo "  9 - Benchmarking"
    echo ""
    echo "Use --confirm to skip confirmation prompt"
    exit 1
}

function verify_git() {
    if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
        echo -e "${RED}ERROR: Not in a git repository${NC}"
        echo "Rollback requires git to restore modified files"
        exit 1
    fi
}

function confirm_rollback() {
    if [ "$CONFIRM" != "--confirm" ]; then
        echo -e "${YELLOW}WARNING: This will rollback Phase $PHASE${NC}"
        echo ""
        echo "Files to be deleted:"
        echo "${PHASE_FILES[$PHASE]}"
        echo ""
        echo "Files to be restored from git:"
        echo "${PHASE_MODIFIED[$PHASE]}"
        echo ""
        read -p "Are you sure you want to proceed? (yes/no): " response

        if [ "$response" != "yes" ]; then
            echo "Rollback cancelled"
            exit 0
        fi
    fi
}

function delete_created_files() {
    echo -e "${YELLOW}Deleting files created in Phase $PHASE...${NC}"

    for file in ${PHASE_FILES[$PHASE]}; do
        if [ -f "$file" ]; then
            echo "  Deleting: $file"
            rm "$file"
        elif [ -d "$file" ]; then
            echo "  Deleting directory: $file"
            rm -rf "$file"
        fi
    done
}

function restore_modified_files() {
    echo -e "${YELLOW}Restoring modified files from git...${NC}"

    for file in ${PHASE_MODIFIED[$PHASE]}; do
        if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
            echo "  Restoring: $file"
            git restore "$file"
        else
            echo "  Skipping (not in git): $file"
        fi
    done
}

function run_regression_tests() {
    echo -e "${YELLOW}Running regression tests...${NC}"

    if ! source .venv/bin/activate 2>/dev/null; then
        echo -e "${RED}WARNING: Could not activate venv${NC}"
    fi

    # Critical regression test
    if pytest tests/test_progressive_discovery.py -v; then
        echo -e "${GREEN}✅ Regression tests PASSED${NC}"
    else
        echo -e "${RED}❌ Regression tests FAILED${NC}"
        echo "The rollback may have introduced issues"
        echo "Manual intervention may be required"
        exit 1
    fi
}

function main() {
    # Validate input
    if [ -z "$PHASE" ]; then
        show_usage
    fi

    if ! [[ "$PHASE" =~ ^[0-9]$ ]]; then
        echo -e "${RED}ERROR: Phase must be 0-9${NC}"
        show_usage
    fi

    # Verify environment
    verify_git

    # Confirm with user
    confirm_rollback

    # Perform rollback
    echo -e "${GREEN}Starting rollback of Phase $PHASE...${NC}"

    delete_created_files
    restore_modified_files
    run_regression_tests

    echo -e "${GREEN}✅ Rollback complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Review the changes with 'git status'"
    echo "2. Re-run full test suite: pytest tests/ -v"
    echo "3. Fix any issues before retrying the phase"
}

main
