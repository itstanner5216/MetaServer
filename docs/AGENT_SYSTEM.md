# AI Agent System Documentation

## Overview

The MetaServer AI Agent System is a fully automated, cloud-based multi-agent system that validates all open PRs, auto-fixes failures, ensures architectural integrity, and generates meta-PRs containing only safe, validated changes.

## System Architecture

The system consists of **6 specialized AI agents** working together:

### 1. **Validation Agent** 🔍

**Purpose:** Sequential validation of all open PRs

**File:** `scripts/agents/validation_agent.py`

**Responsibilities:**
- Fetches all open PRs via GitHub API
- For each PR:
  - Checks out the PR branch
  - Runs full pytest suite with coverage
  - Runs Bandit security scanner
  - Checks for merge conflicts with main
  - Runs `scripts/validate_invariants.py`
  - Verifies pre-commit hooks pass
- Generates conclusive PASS/FAIL verdict per PR
- Outputs: `reports/validation_results.json`

**Output Format:**
```json
{
  "pr_number": 68,
  "title": "Harden inflight lease checks",
  "status": "PASS",
  "tests": {"passed": 347, "failed": 0, "coverage": 94.2},
  "security": {"critical": 0, "high": 0, "medium": 1},
  "conflicts": false,
  "invariants": "PASS",
  "precommit": "PASS",
  "failure_reasons": []
}
```

**Usage:**
```bash
python scripts/agents/validation_agent.py \
  --output reports/validation_results.json
```

---

### 2. **Remediation Agent** 🔧

**Purpose:** Automatically fix common PR failures

**File:** `scripts/agents/remediation_agent.py`

**Capabilities:**

1. **Auto-fix merge conflicts:**
   - Uses strategic merge resolution
   - Attempts `--theirs` and `--ours` strategies
   - Fallback to three-way merge analysis

2. **Patch test failures:**
   - Parses pytest output for failure patterns
   - Applies common fixes (missing imports, fixture errors)
   - Re-runs tests to verify fixes

3. **Fix import errors:**
   - Detects `ModuleNotFoundError`
   - Updates import paths from `src.meta_mcp` → `meta_mcp`
   - Fixes relative imports

4. **Apply security fixes:**
   - Auto-applies Bandit recommendations (low-risk only)
   - Adds input validation where missing
   - Flags high-risk issues for manual review

5. **Commit fixes automatically:**
   - Creates commits on PR branches: `"fix: auto-remediation by AI agent"`
   - Pushes to PR branch (when `--auto-commit` flag used)
   - Re-triggers validation

**Output:** Updated PRs with auto-fix commits + re-validation results

**Usage:**
```bash
python scripts/agents/remediation_agent.py \
  --input reports/validation_results.json \
  --output reports/remediation_results.json \
  --auto-commit
```

**Safety:** Only fixes low-risk, well-understood patterns. High-risk changes require manual review.

---

### 3. **Architectural Guardian Agent** 🏛️

**Purpose:** Ensure PRs don't introduce breaking changes or alter core behavior

**File:** `scripts/agents/architectural_guardian.py`

**Analysis Methods:**

1. **Function Signature Analysis (AST-based):**
   - Detects changes in function arguments
   - Detects changes in return types
   - Detects removed public functions
   - Example:
     ```python
     # BEFORE: def lease_manager.validate(client_id, tool_name)
     # AFTER:  def lease_manager.validate(client_id, tool_name, extra_param)
     # VERDICT: ❌ BREAKING CHANGE
     ```

2. **Data Flow Analysis:**
   - Tracks governance decision flow
   - Ensures flow remains unchanged
   - Flags reordering of critical steps

3. **API Contract Verification:**
   - Checks tool function signatures unchanged
   - Verifies return types preserved
   - Ensures FastMCP decorators consistent

4. **Behavioral Classification:**
   - ✅ **SAFE**: Bug fixes, logging improvements, error handling
   - ⚠️ **REVIEW**: Refactoring, performance optimizations
   - ❌ **REJECT**: New features, breaking changes, behavior modifications

**Specific Rules for MetaServer:**
- ✅ Allow: Internal helper refactoring if public API unchanged
- ✅ Allow: Adding validation/error handling
- ✅ Allow: Fixing race conditions (lease management)
- ⚠️ Flag: Changes to governance flow order
- ❌ Reject: Changing tool schemas without migration
- ❌ Reject: Modifying capability token format
- ❌ Reject: Altering Redis key structures

**Output:**
```json
{
  "pr_number": 90,
  "architectural_verdict": "SAFE",
  "change_classification": "bug_fix",
  "breaking_changes": [],
  "behavioral_changes": ["Added pre-governance hook mutation check"],
  "risk_level": "low",
  "recommendation": "APPROVE"
}
```

**Usage:**
```bash
python scripts/agents/architectural_guardian.py \
  --validation reports/validation_results.json \
  --output reports/architectural_analysis.json
```

---

### 4. **Meta-PR Creator** 📦

**Purpose:** Group and create meta-PRs from safe PRs

**File:** `scripts/agents/meta_pr_creator.py`

**Functionality:**
- Groups PRs by functional area (lease, governance, registry, config, runner)
- Creates meta-PR branches
- Merges PRs with `--no-ff` (preserves commit identity)
- Creates draft PRs with validation proofs
- Includes rollback instructions

**PR Grouping Strategy:**

1. **Meta-PR: Lease & Concurrency Fixes**
   - Keywords: lease, concurrency, inflight, reservation
   
2. **Meta-PR: Hook Mutation & Governance**
   - Keywords: governance, hook, mutation, permission, elevation
   
3. **Meta-PR: Registry & Discovery**
   - Keywords: registry, discovery, tool
   
4. **Meta-PR: Config & Import Fixes**
   - Keywords: config, import, package
   
5. **Meta-PR: Command Runner & Elicitation**
   - Keywords: runner, command, elicitation, result

**Usage:**
```bash
python scripts/agents/meta_pr_creator.py \
  --architectural reports/architectural_analysis.json \
  --output reports/meta_prs_created.json \
  --create-drafts
```

---

### 5. **Functional Verification Agent** ✅

**Purpose:** Verify meta-PRs don't break server functionality

**File:** `scripts/agents/functional_verifier.py`

**Test Suite:**

1. **Integration Tests:**
   - Runs all `tests/integration/` tests
   - Verifies tool discovery flow unchanged
   - Tests governance modes (read_only, permission, bypass)
   - Validates lease management end-to-end

2. **Behavioral Regression Tests:**
   - Compares test results against baseline (main branch)
   - Detects any reduction in passing tests
   - Flags behavioral changes

3. **Performance Benchmarking:**
   - Runs lightweight benchmarks
   - Compares to baseline (main branch)
   - Flags >10% performance degradation
   - Metrics: test execution time

4. **Server Startup & Health:**
   - Verifies module imports work
   - Checks invariant validation passes
   - Confirms no runtime errors

**Output:**
```json
{
  "meta_pr_branch": "meta-lease-fixes",
  "bundled_prs": [68, 69, 71, 74],
  "functional_verdict": "PASS",
  "tests_passed": 347,
  "tests_failed": 0,
  "behavioral_changes_detected": false,
  "performance_delta": "+2.3%",
  "recommendation": "READY_TO_MERGE"
}
```

**Usage:**
```bash
python scripts/agents/functional_verifier.py \
  --meta-prs reports/meta_prs_created.json \
  --output reports/functional_verification.json
```

---

### 6. **Summary Generator** 📊

**Purpose:** Aggregate all agent reports into final summary

**File:** `scripts/agents/generate_summary.py`

**Functionality:**
- Loads all JSON reports
- Generates comprehensive markdown summary
- Creates action items list
- Formats for GitHub step summary

**Usage:**
```bash
python scripts/agents/generate_summary.py \
  --reports-dir reports/ \
  --output reports/FINAL_SUMMARY.md
```

---

## GitHub Actions Workflow

**File:** `.github/workflows/intelligent-pr-validation.yml`

**Trigger:** Manual via workflow_dispatch

**Workflow Inputs:**
- `auto_fix`: Enable auto-remediation agent? (default: true)
- `architectural_check`: Enable architectural guardian? (default: true)
- `create_meta_prs`: Auto-create meta-PRs? (default: true)

**Jobs:**

1. **validate-all-prs**: Runs Validation Agent
2. **auto-remediation**: Runs Remediation Agent (if enabled)
3. **architectural-analysis**: Runs Architectural Guardian (if enabled)
4. **create-meta-prs**: Creates meta-PRs (if enabled)
5. **functional-verification**: Verifies meta-PRs
6. **generate-summary**: Generates final report

**How to Run:**

1. Go to GitHub Actions tab
2. Select "🤖 Intelligent PR Validation & Auto-Remediation"
3. Click "Run workflow"
4. Select options (auto_fix, architectural_check, create_meta_prs)
5. Click "Run workflow"

**Results:**
- Check workflow run for step-by-step progress
- Download artifacts for detailed reports
- View final summary in workflow summary

---

## Safety Mechanisms

### 1. **Dry-run Mode**
Test without creating PRs:
```bash
python scripts/agents/meta_pr_creator.py \
  --architectural reports/architectural_analysis.json \
  --output reports/meta_prs_created.json
  # Omit --create-drafts flag
```

### 2. **Manual Approval Gates**
- Meta-PRs created as **draft PRs**
- Require manual review before merging
- Rollback instructions included

### 3. **Fail-safe Defaults**
- Prefer manual review over auto-merge
- High-risk changes automatically flagged
- Breaking changes automatically rejected

### 4. **Audit Trail**
- All agent actions logged
- Reports stored as artifacts
- Git history preserved with `--no-ff`

### 5. **Rollback Procedures**

If a meta-PR causes issues after merging:

```bash
# Method 1: Revert the merge commit
git revert -m 1 <merge_commit_sha>
git push

# Method 2: Reset to before the merge
git reset --hard <commit_before_merge>
git push --force
```

---

## Handling Edge Cases

### Case 1: PR Validation Timeout
**Problem:** PR takes too long to validate (>90 minutes)

**Solution:**
- Workflow has timeout-minutes: 90
- Failed PRs can be re-validated individually
- Check logs for specific failure

### Case 2: Merge Conflicts During Meta-PR Creation
**Problem:** Conflicting changes between bundled PRs

**Solution:**
- Remediation agent attempts auto-resolution
- If auto-resolution fails, PR excluded from meta-PR
- Manual resolution required

### Case 3: False Positive Breaking Change
**Problem:** Architectural guardian incorrectly flags safe change

**Solution:**
- Review architectural_analysis.json
- Override decision manually
- Update grouping rules if needed

### Case 4: Test Failures in Meta-PR
**Problem:** Tests pass individually but fail when combined

**Solution:**
- Functional verifier detects this
- Meta-PR marked as "DO_NOT_MERGE"
- Manual investigation required

---

## Expected Outcomes

### After Running the System:

**You Get:**
- ✅ 5-7 validated meta-PRs ready to merge
- ✅ Complete validation proof for each
- ✅ Architectural safety guarantees
- ✅ Functional verification results
- ✅ Clear action items for remaining PRs

**You Save:**
- 40+ hours of manual PR review
- Eliminate risk of merging breaking changes
- Confidence that server behavior unchanged

---

## Configuration

### Environment Variables

```bash
# Required
export GITHUB_TOKEN="ghp_xxxxx"  # GitHub API token

# Optional
export REDIS_HOST="localhost"    # For tests
export REDIS_PORT="6379"         # For tests
```

### GitHub Token Permissions

Required scopes:
- `repo` (full control)
- `workflow` (update workflows)
- `write:discussion` (add PR comments)

---

## Troubleshooting

### Issue: "GitHub token required"

**Solution:**
```bash
export GITHUB_TOKEN="your_token_here"
```

### Issue: "Failed to checkout PR branch"

**Cause:** PR branch deleted or repository access issue

**Solution:**
- Verify PR is still open
- Check repository access
- Run `git fetch --all`

### Issue: "Import errors in agent scripts"

**Cause:** Dependencies not installed

**Solution:**
```bash
pip install -e ".[dev]"
pip install httpx pytest pytest-asyncio pytest-cov bandit
```

### Issue: "No PRs found"

**Cause:** No open PRs or GitHub API issue

**Solution:**
- Verify there are open PRs
- Check GitHub token permissions
- Verify repository name is correct

---

## Development

### Running Agents Locally

```bash
# Validation
python scripts/agents/validation_agent.py --output reports/validation_results.json

# Remediation (dry-run, no commits)
python scripts/agents/remediation_agent.py \
  --input reports/validation_results.json \
  --output reports/remediation_results.json

# Architectural Guardian
python scripts/agents/architectural_guardian.py \
  --validation reports/validation_results.json \
  --output reports/architectural_analysis.json

# Meta-PR Creator (dry-run, no GitHub PRs)
python scripts/agents/meta_pr_creator.py \
  --architectural reports/architectural_analysis.json \
  --output reports/meta_prs_created.json

# Functional Verifier
python scripts/agents/functional_verifier.py \
  --meta-prs reports/meta_prs_created.json \
  --output reports/functional_verification.json

# Summary Generator
python scripts/agents/generate_summary.py \
  --reports-dir reports/ \
  --output reports/FINAL_SUMMARY.md
```

### Adding New Agents

1. Create agent script in `scripts/agents/`
2. Follow existing agent structure (dataclasses, main function)
3. Add to workflow in `.github/workflows/intelligent-pr-validation.yml`
4. Update documentation

### Testing Agents

```bash
# Run validation agent on specific repo
cd /path/to/test/repo
python /path/to/MetaServer/scripts/agents/validation_agent.py

# Test with mock data
python -m pytest tests/agents/test_validation_agent.py
```

---

## Architecture Decisions

### Why AST Analysis?
- Precise detection of API changes
- Language-aware (understands Python semantics)
- Catches subtle breaking changes

### Why --no-ff Merges?
- Preserves individual PR commit history
- Easier to revert specific PRs
- Maintains attribution

### Why Draft PRs?
- Safety: requires manual approval
- Allows review before merge
- Prevents accidental auto-merge

### Why Functional Area Grouping?
- Reduces cognitive load in review
- Related changes reviewed together
- Easier to understand impact

---

## Future Enhancements

1. **Machine Learning Integration:**
   - Learn from historical PR patterns
   - Improve auto-fix accuracy
   - Predict merge conflicts

2. **Advanced Conflict Resolution:**
   - Semantic merge strategies
   - Use of git rerere database
   - AI-powered conflict resolution

3. **Performance Optimization:**
   - Parallel PR validation
   - Caching of test results
   - Incremental analysis

4. **Enhanced Reporting:**
   - Interactive dashboards
   - Trend analysis
   - PR health metrics

---

## Support

For issues or questions:
1. Check this documentation
2. Review workflow logs
3. Check agent output in reports/
4. Open an issue on GitHub

---

**Last Updated:** 2026-01-14  
**Version:** 1.0.0  
**Maintainer:** MetaServer Team
