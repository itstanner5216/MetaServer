# PR Consolidation Guide

## Overview

This repository includes automation to manage duplicate PRs and keep the PR list clean.

## Quick Start

### Analyze PRs (Safe - No Changes)
```bash
python scripts/consolidate_prs.py \
  --repo itstanner5216/MetaServer \
  --token $GITHUB_TOKEN
```

### Consolidate PRs (Closes Duplicates)
```bash
python scripts/consolidate_prs.py \
  --repo itstanner5216/MetaServer \
  --token $GITHUB_TOKEN \
  --execute
```

### Clean Up AI Comments
```bash
python scripts/cleanup_ai_comments.py \
  --repo itstanner5216/MetaServer \
  --token $GITHUB_TOKEN \
  --execute
```

## Using GitHub Actions Workflow

Navigate to: **Actions → PR Consolidation and Cleanup → Run workflow**

### Modes

1. **analyze_only** - Shows what would be closed (no changes)
2. **consolidate_prs** - Closes duplicate PRs
3. **cleanup_comments** - Removes old AI review comments
4. **full_process** - Does all of the above + re-runs AI review

### Full Process Flow

When you run in `full_process` mode:

1. **Analyze** all open PRs
2. **Group** duplicates by issue signature and base branch
3. **Score** each PR based on quality heuristics
4. **Keep** the best PR from each group
5. **Close** duplicates with explanatory comments
6. **Delete** old AI review comments from remaining PRs
7. **Trigger** fresh AI review pipeline run
8. **Generate** summary artifact

## How Duplicates Are Detected

PRs are considered duplicates if they:
- Target the same base branch
- Have similar titles (normalized)
- Address the same core issue (extracted from title/body)

## How the "Best" PR Is Selected

Quality score based on:
- ✅ Targets `main` branch (+10 points)
- ✅ Smaller, focused changes (+5 points if <100 lines)
- ✅ More recent (+1 point)
- ✅ Includes tests (+3 points)
- ❌ Missing test execution (-2 points)

## Safety Features

- **Dry-run by default** - Must explicitly pass `--execute`
- **Preserves one PR per issue** - Never closes all PRs in a group
- **Base branch aware** - PRs to different branches can coexist
- **Explanatory comments** - Closed PRs get a comment explaining why
- **Summary artifact** - Full report of what was closed and why

## Examples

### Scenario: 93 PRs, Many Duplicates

**Before:**
- 93 open PRs
- 15 different fixes for "governance hook mutation" issue
- 10 different fixes for "lease overuse" issue
- Hard to know which to review

**After:**
- ~15-20 open PRs
- 1 PR per unique issue
- Clear which PRs need review
- Old AI comments removed, fresh reviews posted

## Troubleshooting

**Q: What if the wrong PR was kept?**
A: Re-open the closed PR and manually close the other one. The selection is heuristic-based.

**Q: Can I prevent a specific PR from being closed?**
A: Yes, add a label `keep-open` or similar, then update the script to skip PRs with that label.

**Q: Will this delete my manual comments?**
A: No, only comments from `github-actions[bot]` containing AI review patterns are deleted.

## Testing Strategy

Before running in production:

1. **Test on a fork first** with `analyze_only` mode
2. **Review the summary** to ensure grouping makes sense
3. **Manually verify** a few "best" PR selections
4. **Run consolidate** with `--execute`
5. **Check results** and adjust scoring heuristics if needed

## Success Criteria

1. ✅ Duplicate PRs are correctly identified and grouped
2. ✅ The "best" PR from each group is retained
3. ✅ Closed PRs have explanatory comments
4. ✅ Old AI review comments are removed
5. ✅ Fresh AI reviews are posted to remaining PRs
6. ✅ Summary artifact shows what happened
7. ✅ Final PR count is ~10-20 instead of 93
