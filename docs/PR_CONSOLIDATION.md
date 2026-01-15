# PR Consolidation & Cleanup Workflow

Automated three-phase workflow to consolidate duplicate PRs, clean up outdated AI review comments, and trigger fresh AI reviews.

## 🎯 Overview

The **PR Consolidation workflow** helps manage repositories with many open PRs by:

1. **Analyzing** all open PRs and categorizing them by issue type
2. **Closing** duplicate PRs while keeping the highest-quality one per category
3. **Cleaning** outdated AI review comments from remaining PRs
4. **Re-running** AI reviews with accurate test results

## 📊 Problem Statement

This workflow solves the following issues:

- **93+ open PRs** with many duplicates
- **Overlapping fixes** for the same issues
- **Outdated AI comments** with incorrect test results
- **Difficulty** determining which PRs are valuable
- **Cluttered** PR review experience

## 🚀 Usage

### Step 1: Dry Run (Recommended)

Run the workflow in **dry-run mode** first to see what would happen:

1. Go to **Actions** → **🧹 PR Consolidation & Cleanup**
2. Click **Run workflow**
3. Configure inputs:
   - ✅ **Dry run mode**: `true` (enabled)
   - ✅ **Auto cleanup comments**: `true` (enabled)
   - ✅ **Auto rerun pipeline**: `true` (enabled)
4. Click **Run workflow**

This will:
- Analyze all PRs and generate a report
- Show which PRs would be closed
- NOT make any actual changes

### Step 2: Review the Report

1. Wait for the workflow to complete
2. Download the **consolidation-report** artifact
3. Review `consolidation-report.json` to see:
   - Which PRs will be kept
   - Which PRs will be closed
   - Category classifications
   - PR scores

### Step 3: Execute Consolidation

If the report looks good, run the workflow again:

1. Go to **Actions** → **🧹 PR Consolidation & Cleanup**
2. Click **Run workflow**
3. Configure inputs:
   - ❌ **Dry run mode**: `false` (disabled)
   - ✅ **Auto cleanup comments**: `true` (enabled)
   - ✅ **Auto rerun pipeline**: `true` (enabled)
4. Click **Run workflow**

This will:
1. Close duplicate PRs with explanatory comments
2. Delete old AI review comments from remaining PRs
3. Trigger fresh AI reviews

## 📁 PR Categories

PRs are automatically categorized by keywords in their title and description:

| Category | Keywords | Example Issues |
|----------|----------|----------------|
| **governance-hook-mutations** | governance, before_tool, hook, mutate, mutation, re-evaluate | Governance bypass via hooks |
| **lease-overuse** | lease, overuse, concurrent, race, reserve, refund, consume | Lease consumption race conditions |
| **import-fixes** | modulenotfound, import, src.meta_mcp, meta_mcp.config | Import path and module errors |
| **test-fixes** | test, pytest, automated tests | Test infrastructure improvements |
| **command-execution** | command, execute_command, subprocess, command_runner | Command execution refactoring |
| **discovery-registry** | discovery, registry, tool_registry, bootstrap | Tool discovery system changes |
| **elicitation** | elicit, approval, fastmcp, structured response | Approval request parsing |
| **pipeline-workflow** | ai agent pipeline, workflow, ai-pr-review, secret | AI pipeline configuration |
| **other** | - | Uncategorized PRs |

## 🏆 PR Scoring Algorithm

For each category with multiple PRs, the workflow scores them and keeps the highest-scoring one:

| Factor | Points | Rationale |
|--------|--------|-----------|
| Targets `main` branch | +20 | Preferred merge destination |
| Non-draft status | +10 | Ready for review |
| Has assignees | +5 | Human attention |
| Has reviewers | +5 | Under active review |
| Description quality | +0 to +10 | More details = better |
| Recency | +0 to +10 | Newer PRs preferred |
| Created by bot | -5 | Prefer human-created PRs |

**The PR with the highest score in each category is kept; all others are closed.**

## 🔄 Three-Phase Process

### Phase 1: Analyze & Close Duplicates

**Jobs:**
- `analyze-prs` - Categorizes and scores all PRs
- `close-duplicate-prs` - Closes lower-scored duplicates (skipped in dry-run)

**Outputs:**
- List of PRs to keep
- List of PRs to close
- Consolidation report (JSON)

### Phase 2: Clean Up AI Comments

**Job:** `cleanup-comments`

Removes outdated AI review comments from remaining PRs:
- Searches for comments from `github-actions` bot
- Matches signature patterns:
  - "AI-Powered PR Review Pipeline"
  - "Validation Agent"
  - "Remediation Agent"
  - "Architectural Guardian"
  - "Functional Verifier"
- Deletes matching comments
- Posts a single cleanup notice

### Phase 3: Re-run AI Reviews

**Job:** `rerun-ai-pipeline`

Triggers the `ai-pr-review-pipeline.yml` workflow with:
- Comma-separated list of remaining PR numbers
- `review_and_fix` mode
- Fresh reviews with accurate test results

## 📋 Workflow Summary

**Job:** `summary`

Generates a comprehensive summary showing:
- Total PRs analyzed
- PRs to keep vs. close
- Category breakdown
- List of actions taken
- Next steps

## 🛡️ Safety Features

1. **Dry-run by default** - Must explicitly disable to make changes
2. **Explanation comments** - Each closed PR receives a detailed comment explaining why
3. **Reopen instructions** - Users can contest closures and tag maintainers
4. **Downloadable reports** - Full analysis saved as artifact (30-day retention)
5. **Gradual execution** - Three separate phases with checkpoints
6. **Conditional execution** - Later phases only run if earlier phases succeed

## 📊 Expected Outcome

### Before

- **93+ open PRs**
- Many duplicate fixes for the same issues
- Conflicting solutions
- Outdated AI comments with incorrect test results
- Difficult to identify valuable PRs

### After

- **~10-15 consolidated PRs**
- Each represents a distinct fix
- No duplicates
- Fresh AI review comments
- Accurate test results
- Clear path to merging

## 🔍 Example Workflow Run

### Dry Run Output

```
📊 Consolidation Summary:
  Total PRs: 93
  PRs to keep: 12
  PRs to close: 81

📁 Categories:
  governance-hook-mutations: 15 PRs → Keep PR #145
  lease-overuse: 12 PRs → Keep PR #178
  import-fixes: 8 PRs → Keep PR #192
  test-fixes: 5 PRs → Keep PR #201
  ...
```

### Actual Execution Output

```
Phase 1: Closed 81 duplicate PRs
Phase 2: Deleted 324 outdated AI comments from 12 PRs
Phase 3: Triggered AI reviews for PRs: 145,178,192,201,...
```

## 🎯 Next Steps After Running

1. **Monitor AI reviews** - Check remaining PRs for new AI feedback
2. **Address blockers** - Fix any issues identified by AI agents
3. **Merge approved PRs** - PRs with ✅ status can be merged
4. **Handle reopened PRs** - Review any PRs that users reopened with justification

## ⚙️ Configuration

The workflow is configured via inputs when triggered:

```yaml
inputs:
  dry_run:
    description: 'Dry run mode (analyze only, do not close PRs)'
    type: boolean
    default: true

  auto_cleanup_comments:
    description: 'Automatically clean up comments after consolidation'
    type: boolean
    default: true

  auto_rerun_pipeline:
    description: 'Automatically re-run AI review pipeline after cleanup'
    type: boolean
    default: true
```

## 🔐 Required Permissions

The workflow requires:

```yaml
permissions:
  contents: write        # To checkout repository
  pull-requests: write   # To close PRs and manage comments
  actions: write         # To trigger ai-pr-review-pipeline workflow
```

## 📦 Dependencies

- `actions/checkout@v4` - Repository checkout
- `actions/github-script@v7` - GitHub API interactions
- `actions/upload-artifact@v4` - Report artifact upload

## 🔧 Integration with AI Review Pipeline

This workflow is designed to work with `ai-pr-review-pipeline.yml`:

1. **Run PR Consolidation** - Reduces PRs and cleans comments
2. **Auto-triggers AI Pipeline** - Fresh reviews on remaining PRs
3. **Wait for AI reviews** - Check consolidated PRs for feedback
4. **Merge when ready** - PRs with ✅ can be merged

## 🐛 Troubleshooting

### "No PRs to close" in dry-run

**Cause:** All PRs are in different categories or there's only one PR per category

**Solution:** This is expected - the workflow keeps PRs that don't have duplicates

### Closed PR should have been kept

**Cause:** Scoring algorithm favored a different PR

**Solution:**
1. Reopen the PR
2. Comment explaining why it should be kept
3. Tag @itstanner5216
4. Close the duplicate manually

### AI pipeline not triggered

**Cause:** `auto_rerun_pipeline` was set to `false` or Phase 2 failed

**Solution:** Manually trigger `ai-pr-review-pipeline.yml` with the PR numbers from the report

### Comment cleanup deleted important comments

**Cause:** Comment matched one of the AI signature patterns

**Solution:** AI comments are recreated in Phase 3; important non-AI comments won't match the patterns

## 📚 Related Documentation

- [AI Agent Pipeline](./AI_AGENT_PIPELINE.md) - Details on the AI review system
- [Contributing Guide](../CONTRIBUTING.md) - PR contribution guidelines
- [Workflow File](../.github/workflows/pr-consolidation.yml) - Source code

## 🤝 Contributing

To improve this workflow:

1. Test changes with `dry_run: true` first
2. Update this documentation
3. Submit a PR with your improvements
4. Tag @itstanner5216 for review

## 📝 Notes

- The workflow runs **manually** via `workflow_dispatch` only
- It does **not** run automatically on PR events
- **Dry-run mode is the default** to prevent accidental closures
- The consolidation report is retained for **30 days**
- Closed PRs can be **reopened** by users or maintainers

## 💡 Tips

- Run dry-run mode first to preview changes
- Download and review the consolidation report before executing
- Consider running this after merging a major test infrastructure fix
- Keep an eye on the GitHub Actions summary for execution status
- Use this periodically (e.g., monthly) to keep PRs manageable
