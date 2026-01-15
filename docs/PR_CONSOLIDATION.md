# PR Consolidation Workflow

## Overview

The PR consolidation workflow helps manage large numbers of open PRs by:
1. Grouping similar/duplicate PRs
2. Keeping the highest-quality PR from each group
3. Closing duplicates with explanatory comments
4. Cleaning up stale AI review comments
5. Re-running fresh AI reviews on remaining PRs

## Usage

### Dry Run (Recommended First)

1. Go to Actions → "🧹 PR Consolidation & Cleanup"
2. Click "Run workflow"
3. Set `dry_run: true` (default)
4. Click "Run workflow"
5. Review the consolidation plan in the workflow summary
6. Download the `consolidation-plan` artifact for full details

### Execute Consolidation

1. After reviewing the dry run results
2. Run workflow again with `dry_run: false`
3. Workflow will:
   - Close duplicate PRs
   - Delete AI review comments
   - Trigger fresh reviews

## How PRs Are Scored

The workflow scores PRs based on:
- **+10 points** - Non-draft status
- **+0-10 points** - Recency (newer = better)
- **+0-5 points** - Simplicity (fewer files changed)
- **+15 points** - Targets `main` branch
- **+5 points** - Has assignees/reviewers
- **-10 points** - Older than 7 days

The highest-scoring PR in each similarity group is kept.

## Similarity Detection

PRs are grouped if they:
- Target the same base branch
- Have >40% keyword overlap in title + description
- Address similar issues (e.g., "fix governance hook mutation")

## Configuration

You can adjust:
- `min_prs_to_keep` - Target number of PRs (default: 10)
- `max_prs_to_keep` - Maximum PRs to keep (default: 15)
- `dry_run` - Preview mode (default: true)

## Safety Features

- **Dry run by default** - Always previews before executing
- **Preserves quality** - Keeps best PR from each group
- **Explanatory comments** - Closed PRs get context
- **Artifact logs** - Full consolidation plan saved
- **Rate limiting** - Avoids GitHub API throttling
