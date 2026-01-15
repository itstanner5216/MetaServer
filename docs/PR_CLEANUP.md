# PR Cleanup & Consolidation Guide

## Overview

This repository has automated workflows to manage PR consolidation and AI review comment cleanup.

## Workflows

### 1. PR Consolidation (`pr-consolidation.yml`)

**Purpose:** Analyze open PRs, identify duplicates, and close them.

**Usage:**
```bash
# Dry run (analyze only, no changes)
gh workflow run pr-consolidation.yml -f dry_run=true

# Execute (actually close PRs)
gh workflow run pr-consolidation.yml -f dry_run=false
```

**What it does:**
- Groups PRs by issue type and base branch
- Scores PRs based on quality indicators
- Keeps the best PR from each group
- Closes duplicates with explanatory comments

### 2. Comment Cleanup (`cleanup-pr-comments.yml`)

**Purpose:** Delete stale AI review comments from PRs.

**Usage:**
```bash
# Clean all open PRs
gh workflow run cleanup-pr-comments.yml -f pr_numbers=all

# Clean specific PRs
gh workflow run cleanup-pr-comments.yml -f pr_numbers="1,2,3,5,8"
```

### 3. Re-run Reviews (`rerun-pr-reviews.yml`)

**Purpose:** Trigger fresh AI reviews on PRs.

**Usage:**
```bash
# Review all open PRs
gh workflow run rerun-pr-reviews.yml -f pr_numbers=all -f agent_mode=review_and_fix
```

### 4. Full Cleanup (`full-cleanup.yml`)

**Purpose:** Run all three steps in sequence.

**Usage:**
```bash
# Full automated cleanup
gh workflow run full-cleanup.yml
```

**What it does:**
1. Consolidates duplicate PRs
2. Cleans up stale comments
3. Re-runs AI reviews with fresh tests

## Workflow

### Initial Setup
1. Run consolidation in dry-run mode to review
2. Check the consolidation report artifact
3. Run consolidation for real if satisfied

### Regular Maintenance
1. Use `full-cleanup.yml` monthly to keep PRs organized
2. Run `cleanup-pr-comments.yml` after major test suite changes
3. Use `rerun-pr-reviews.yml` to refresh reviews as needed

## Safety Features

- **Dry run mode** - Preview changes before executing
- **Detailed reports** - Review what will be closed
- **Explanatory comments** - Closed PRs include reasons
- **Reversible** - Closed PRs can be reopened if needed

## Monitoring

All workflows generate detailed summaries in the Actions tab. Check:
- Consolidation reports (downloadable artifacts)
- Comment deletion counts
- Review trigger confirmations
