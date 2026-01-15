# PR Consolidation Workflow

## Overview

This workflow helps manage PR sprawl by automatically identifying and closing duplicate PRs while preserving the highest-quality version of each proposed change.

## How It Works

### Phase 1: Analysis
1. Fetches all open PRs (handles pagination automatically)
2. Groups PRs by keyword similarity (configurable threshold)
3. Scores each PR based on quality factors:
   - **Recency** (0-10 points): Newer PRs score higher
   - **Non-draft status** (+10 points): Complete PRs preferred
   - **Targets main branch** (+15 points): Main branch PRs prioritized
   - **Has assignees** (+5 points): Assigned work is valued
   - **Focused title** (+5 points): Titles under 80 characters
   - **Has labels** (+2 per label, max 6): Properly categorized PRs
   - **Clean discussion** (+3 points): Fewer than 5 comments

### Phase 2: Consolidation
1. Selects highest-scoring PR from each group as the "keeper"
2. Closes duplicates with explanatory comments
3. Cleans up stale AI review comments from keeper PRs
4. Re-runs AI review pipeline with fresh context (optional)

### Phase 3: Reporting
Generates detailed summary showing what was kept, what was closed, and why.

## Usage

### Dry Run (Recommended First)

1. Go to **Actions** → **🧹 PR Consolidation & Cleanup**
2. Click **Run workflow**
3. Leave `dry_run: true` ✅ (default)
4. Set `min_similarity_threshold` if needed (default: 40%)
5. Review the summary in the workflow run
6. Download `consolidation-plan.json` artifact for full details
7. Verify the plan looks correct

### Live Run

1. Re-run the workflow from Actions
2. Set `dry_run: false` ❌
3. Optionally adjust `min_similarity_threshold` (default: 40%)
4. Set `re_run_reviews: true` if you want fresh AI reviews
5. Confirm and run

## Safety Features

- ✅ **Dry run by default** - Always preview before executing
- ✅ **Explanatory comments** - Closed PRs receive detailed explanations
- ✅ **Audit trail** - Full consolidation plan saved as artifact
- ✅ **Rate limiting** - Respects GitHub API limits with delays
- ✅ **Same-base-branch grouping** - Never groups PRs with different target branches
- ✅ **Idempotent** - Safe to run multiple times
- ✅ **Keep-open label protection** - PRs with `keep-open` label are never closed
- ✅ **Recency protection** - PRs created in the last 6 hours are not closed
- ✅ **Bulk closure safety** - Workflow fails if trying to close more than 50 PRs

## Workflow Inputs

### `dry_run` (boolean, default: true)
- **true**: Preview mode - shows what would happen without making changes
- **false**: Live mode - actually closes PRs and cleans up comments

### `min_similarity_threshold` (number, default: 40)
- Minimum percentage of keyword overlap to group PRs together
- Range: 0-100
- **Lower (20-30%)**: More aggressive grouping, closes more PRs
- **Higher (50-70%)**: Conservative grouping, keeps more PRs
- **Default (40%)**: Balanced approach

### `re_run_reviews` (boolean, default: true)
- **true**: Triggers AI review pipeline for keeper PRs after cleanup
- **false**: Skips AI review re-run (useful for manual review)

## Grouping Algorithm

The workflow uses a keyword-based similarity algorithm to identify duplicate PRs:

1. **Keyword Extraction**: Extracts relevant keywords from PR title and body
   - Keywords: governance, lease, hook, mutation, config, import, test, redis, refactor, tool, call, path, fix, update

2. **Similarity Calculation**: Uses Jaccard similarity
   - Similarity = (Intersection of keywords) / (Union of keywords)
   - PRs must also target the same base branch

3. **Theme Inference**: Automatically categorizes PRs into themes:
   - Governance Hook Mutation Fixes
   - Lease Management Improvements
   - Import Path Fixes
   - Test Infrastructure
   - Redis Integration
   - Configuration Updates
   - Code Refactoring
   - Tool Call Mutation Handling
   - General Improvements

## Quality Scoring

Each PR receives a score based on multiple factors:

```
Score Breakdown:
- Recency: 0-10 points (newer = higher)
- Not draft: +10 points
- Targets main: +15 points
- Has assignees: +5 points
- Title < 80 chars: +5 points
- Labels: +2 per label (max +6)
- Comments < 5: +3 points

Maximum possible score: ~53 points
```

The PR with the highest score in each group is kept; others are closed.

## Workflow Jobs

### 1. `analyze-prs`
- Fetches all open PRs with pagination
- Filters out PRs with `keep-open` label
- Filters out PRs created in the last 6 hours
- Groups similar PRs by keyword matching
- Scores each PR and selects keepers
- Generates consolidation plan
- Creates detailed summary
- Saves plan as JSON artifact

### 2. `close-duplicates`
- Depends on: `analyze-prs`
- Validates closure count (max 50 PRs)
- Posts explanatory comment on each duplicate PR
- Closes duplicate PRs
- Includes rate limiting (2 seconds between closures)

### 3. `cleanup-comments`
- Depends on: `analyze-prs`, `close-duplicates`
- Fetches comments from keeper PRs
- Identifies stale AI review comments:
  - "AI-Powered PR Review Pipeline"
  - "🔍 Validation Agent"
  - "🔧 Remediation Agent"
  - "🏛️ Architectural Guardian"
  - "✅ Functional Verifier"
- Deletes matching comments
- Includes rate limiting (500ms between deletions)

### 4. `re-run-reviews`
- Depends on: `analyze-prs`, `cleanup-comments`
- Only runs if `dry_run: false` and `re_run_reviews: true`
- Triggers `ai-pr-review-pipeline.yml` workflow
- Passes keeper PR numbers for fresh reviews

### 5. `generate-summary`
- Runs always (even if previous jobs fail)
- Aggregates results from all jobs
- Creates comprehensive summary with:
  - Job statuses
  - PRs kept and closed
  - Next steps
  - Full audit trail

## Customization

### Adjusting Keyword Matching

Edit the `keywords` array in `.github/workflows/pr-consolidation.yml` (line ~161):

```javascript
const keywords = ['governance', 'lease', 'hook', 'mutation', 'config', 'import', 'test', 'redis', 'refactor', 'tool', 'call', 'path', 'fix', 'update'];
```

Add or remove keywords relevant to your repository's common PR patterns.

### Modifying Quality Scoring

Edit the `scorePR()` function in the workflow (lines ~172-195) to adjust scoring weights:

```javascript
function scorePR(pr) {
  let score = 0;
  
  // Customize weights here
  if (!pr.draft) score += 10;  // Increase/decrease as needed
  if (pr.base.ref === 'main') score += 15;  // Adjust priority
  
  // Add custom scoring criteria
  if (pr.title.includes('[URGENT]')) score += 20;
  
  return Math.round(score * 10) / 10;
}
```

### Adding Theme Categories

Edit the `inferTheme()` function (lines ~149-159) to add custom themes:

```javascript
function inferTheme(pr) {
  const text = (pr.title + ' ' + pr.body).toLowerCase();
  
  // Add your custom themes
  if (text.includes('security') && text.includes('fix')) return 'Security Fixes';
  if (text.includes('performance')) return 'Performance Improvements';
  
  // ... existing themes ...
  return 'General Improvements';
}
```

## Troubleshooting

### A PR was closed that shouldn't have been

**Solution:**
1. Reopen the PR manually
2. Add the `keep-open` label to prevent future auto-closure
3. Tag @itstanner5216 in a comment explaining why it should stay open
4. Future consolidation runs will skip this PR

### The workflow didn't group similar PRs

**Possible causes:**
- Similarity threshold too high
- PRs target different base branches
- Different keyword sets

**Solutions:**
1. Lower `min_similarity_threshold` (try 30% instead of 40%)
2. Review keyword list and add missing terms
3. Check that PRs actually target the same branch

### Too many PRs were kept

**Possible causes:**
- Similarity threshold too high
- PRs are genuinely unique
- Quality scoring doesn't differentiate well

**Solutions:**
1. Raise the threshold (try 50-60%)
2. Adjust quality scoring weights to better differentiate
3. Review themes - may need better categorization

### Workflow failed with "too many PRs to close"

**Cause:** Safety limit prevents closing more than 50 PRs in one run

**Solutions:**
1. Increase similarity threshold to reduce closures
2. Manually review and close some PRs first
3. Run workflow multiple times with different thresholds

### AI review pipeline didn't trigger

**Possible causes:**
- `re_run_reviews` was set to false
- Workflow is in dry run mode
- `ai-pr-review-pipeline.yml` workflow not found

**Solutions:**
1. Ensure `dry_run: false` and `re_run_reviews: true`
2. Check that `ai-pr-review-pipeline.yml` exists in `.github/workflows/`
3. Verify workflow has correct permissions

## Best Practices

1. **Always dry-run first**
   - Review the consolidation plan before executing
   - Verify grouping logic makes sense for your PRs

2. **Run after major test fixes**
   - Clean up stale AI reviews that were based on broken tests
   - Get fresh, accurate reviews on keeper PRs

3. **Manually review keeper PRs**
   - Just because a PR was kept doesn't mean it's ready to merge
   - Review AI comments and verify changes

4. **Set up branch protection**
   - Prevent future PR sprawl with stricter merge requirements
   - Require reviews, passing tests, etc.

5. **Run periodically**
   - Consider running weekly or after major refactors
   - Prevents accumulation of duplicate PRs

6. **Monitor the artifacts**
   - Download and review `consolidation-plan.json`
   - Keep records for audit purposes

7. **Customize for your workflow**
   - Adjust scoring weights based on your priorities
   - Add repository-specific keywords and themes

## Example Workflow Run

### Initial State
- 93 open PRs
- Many duplicates addressing same issues
- Stale AI comments from broken test suite

### Dry Run
```
Actions → PR Consolidation & Cleanup → Run workflow
  dry_run: true
  min_similarity_threshold: 40
  re_run_reviews: true
```

**Result:**
- 12 groups identified
- 13 PRs would be kept
- 80 PRs would be closed
- Review plan in summary and artifact

### Live Run
```
Actions → PR Consolidation & Cleanup → Run workflow
  dry_run: false
  min_similarity_threshold: 40
  re_run_reviews: true
```

**Result:**
- 80 duplicate PRs closed with explanatory comments
- 247 stale AI comments deleted
- AI review pipeline triggered for 13 keeper PRs
- Repository reduced from 93 → 13 high-quality PRs

## Architecture

The workflow is designed to be:

- **Safe**: Multiple safety guards prevent accidental data loss
- **Transparent**: Full audit trail and explanatory comments
- **Configurable**: Easy to customize for different repositories
- **Efficient**: Rate-limited to respect GitHub API limits
- **Idempotent**: Safe to run multiple times

## Related Workflows

- **AI PR Review Pipeline** (`ai-pr-review-pipeline.yml`): Automatically reviews and suggests fixes for PRs
- **Intelligent PR Validation** (`intelligent-pr-validation.yml`): Validates PR structure and content

## Support

For issues, questions, or suggestions:
1. Review this documentation
2. Check the workflow run summary and artifacts
3. Review closed PRs for explanation comments
4. Tag @itstanner5216 in a GitHub issue or PR comment

## Version History

- **v1.0** (2026-01-15): Initial implementation
  - Automated PR grouping and consolidation
  - Stale comment cleanup
  - AI review re-triggering
  - Comprehensive safety guards and reporting
