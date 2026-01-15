# PR Consolidation & Cleanup Scripts

This directory contains scripts for automating PR consolidation and cleanup.

## Overview

The repository contains 93+ open pull requests with many duplicates, conflicts, and stale AI review comments. These scripts help consolidate PRs and clean up the noise.

## Scripts

### 1. `consolidate_prs.py` - PR Consolidation

Analyzes open PRs, groups duplicates/similar PRs, and closes redundant ones in favor of the best solution.

**Features:**
- Fetches all open PRs via GitHub API
- Groups PRs by base branch and issue keywords
- Ranks PRs by quality (recency, merge state, commit count, description)
- Keeps the highest-ranked PR per group
- Closes others with explanatory comments

**Usage:**

```bash
# Preview what would be consolidated (safe)
export GITHUB_TOKEN="your-token"
export GITHUB_REPOSITORY="itstanner5216/MetaServer"
python scripts/consolidate_prs.py --dry-run

# Actually consolidate PRs (closes duplicates)
python scripts/consolidate_prs.py --execute
```

**Output:**
- Console report showing PRs kept/closed
- Closes duplicate PRs with explanation comments
- Links closed PRs to their "winner"

### 2. `cleanup_ai_comments.py` - AI Comment Cleanup

Deletes stale AI review comments from the review pipeline.

**Features:**
- Identifies AI-generated review comments by markers
- Supports specific PRs or all open PRs
- Dry-run mode for safety
- Tracks deletion count

**Usage:**

```bash
# Clean specific PRs (dry-run)
export GITHUB_TOKEN="your-token"
export GITHUB_REPOSITORY="itstanner5216/MetaServer"
python scripts/cleanup_ai_comments.py --prs 12,34,56 --dry-run

# Clean all open PRs (execute)
python scripts/cleanup_ai_comments.py --all

# Clean all open PRs (dry-run)
python scripts/cleanup_ai_comments.py --all --dry-run
```

**AI Comment Markers:**
- `AI-Powered PR Review Pipeline`
- `🔍 Validation Agent`
- `🔧 Remediation Agent`
- `🏛️ Architectural Guardian`
- `✅ Functional Verifier`

## GitHub Actions Workflow

### `pr-consolidation.yml` - Automated Orchestration

Orchestrates all three phases:
1. **Phase 1:** Consolidate duplicate PRs
2. **Phase 2:** Delete stale AI comments from remaining PRs
3. **Phase 3:** Re-run AI review pipeline on remaining PRs

**Trigger:**
- Manual via GitHub UI: Actions → 🔄 PR Consolidation & Cleanup

**Modes:**
- **dry-run** (default): Preview actions without executing
- **execute**: Actually close PRs and delete comments

**Outputs:**
- Consolidation report artifact
- Workflow summary
- Fresh AI reviews on remaining PRs

## Safety Features

- ✅ **Dry-run mode** - Preview before executing
- ✅ **Detailed logging** - Track every action
- ✅ **Explanatory comments** - Closed PRs link to winner
- ✅ **Manual trigger** - No automatic execution
- ✅ **Reversible** - Can reopen PRs if needed

## Dependencies

Required Python packages (installed automatically in workflow):
- `httpx>=0.27.0` - HTTP client for GitHub API

Install locally:
```bash
pip install httpx
```

Or install with scripts extras:
```bash
pip install -e ".[scripts]"
```

## Example Workflow Run

1. Navigate to Actions → 🔄 PR Consolidation & Cleanup
2. Click "Run workflow"
3. Select mode: `dry-run` (recommended first)
4. Review the consolidation report artifact
5. If satisfied, run again with mode: `execute`
6. Review remaining PRs with fresh AI comments

## Expected Results

- **Before:** 93+ open PRs with duplicates and stale comments
- **After:** ~10-15 high-quality PRs with fresh reviews
- **Closed PRs:** Have explanatory comments linking to winner
- **Remaining PRs:** Clean of stale AI comments, fresh reviews

## Troubleshooting

### "GITHUB_TOKEN required"
Set the environment variable:
```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

### "Module 'httpx' not found"
Install dependencies:
```bash
pip install httpx
```

### Rate limiting
The workflow includes rate limit delays. For local runs, add delays between API calls if needed.

## Contributing

These scripts are designed to be run once or periodically to clean up PR clutter. Modify the grouping/ranking logic in `consolidate_prs.py` if needed for your use case.
