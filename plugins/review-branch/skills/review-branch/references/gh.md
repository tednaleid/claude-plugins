# gh cheatsheet for review-branch

`gh` is the GitHub CLI. The skill uses these specific invocations.

## PR metadata

```bash
gh pr view <n> --json number,title,state,author,body,headRefName,baseRefName,headRefOid,url,additions,deletions,changedFiles,commits
```

Key fields:

- `number`, `title`, `state` (`OPEN`, `CLOSED`, `MERGED`)
- `author.login`, `author.name`
- `headRefName` (source branch), `baseRefName` (target branch)
- `headRefOid` (commit SHA at the PR head; useful for round detection)
- `url` -- direct link for the meta row
- `additions`, `deletions`, `changedFiles` -- diff stats
- `commits[].oid`, `commits[].messageHeadline` -- commit list

The full `--json` field set is large; check `gh pr view --json help` (errors out and lists every field).

## Diff

```bash
gh pr diff <n>
```

Outputs unified diff text. Same shape as `glab mr diff`.

For a structured changed-files list:

```bash
gh pr view <n> --json files --jq '.files[] | "\(.path)\t+\(.additions)\t-\(.deletions)"'
```

## Prior discussion (the prior-comments seed)

GitHub PRs have **three** sources of prior context, all distinct:

1. **Top-level conversation comments** (`gh pr view <n> --json comments`):
   ```bash
   gh pr view <n> --json comments --jq '.comments[] | {author: .author.login, body, createdAt}'
   ```
   These are issue-style comments not anchored to any line.

2. **Review submissions** (`gh pr view <n> --json reviews`):
   ```bash
   gh pr view <n> --json reviews --jq '.reviews[] | {author: .author.login, state, body, submittedAt}'
   ```
   Each review has a `state` (`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`) and an optional summary `body`. The summary often has the highest-level feedback.

3. **Inline review comments** (the per-line code comments -- this is where most regression-detection matters):
   ```bash
   OWNER_REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
   gh api "repos/${OWNER_REPO}/pulls/<n>/comments" \
     --jq '.[] | {path, line, body, user: .user.login}'
   ```
   These are NOT in the `--json reviews` field -- the `reviews` field has the summary, the `pulls/.../comments` REST endpoint has the line-anchored bodies.

The human-readable aggregation is `gh pr view <n> --comments` -- it shows all three surfaces concatenated as markdown, in chronological order. Good for piping to a file the lens prompts read.

For seed-context use:

```bash
gh pr view <n> --comments > /tmp/pr-<n>-prior-comments.md
```

Or, for structured per-source dumps:

```bash
OWNER_REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
{
  echo "## Top-level comments"
  gh pr view <n> --json comments --jq '.comments[] | "- @\(.author.login) (\(.createdAt)): \(.body[0:200])"'
  echo
  echo "## Review summaries"
  gh pr view <n> --json reviews --jq '.reviews[] | "- @\(.author.login) [\(.state)]: \(.body[0:200])"'
  echo
  echo "## Inline review comments"
  gh api "repos/${OWNER_REPO}/pulls/<n>/comments" \
    --jq '.[] | "- @\(.user.login) at \(.path):\(.line // .original_line): \(.body[0:200])"'
} > /tmp/pr-<n>-prior-comments.md
```

## Resolved review threads

GitHub has the concept of "resolved" review threads (clicked the "Resolve conversation" button). These don't disappear from the REST endpoint but they have `in_reply_to_id` chains and a separate GraphQL field for `isResolved`. If filtering is needed:

```bash
gh api graphql -f query='
  query($owner: String!, $repo: String!, $n: Int!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $n) {
        reviewThreads(first: 100) {
          nodes { isResolved comments(first: 50) { nodes { body path line author { login } } } }
        }
      }
    }
  }' -F owner=... -F repo=... -F n=<n>
```

Filter `isResolved == false` for unresolved threads.

For the seed-context use case, the simpler `--comments` view is usually enough -- the lens prompts can tell the model "do not re-raise topics that look resolved."

## Recognize a prior Claude review

Same pattern as `glab.md`: if a previous run posted comments, they'll have a footer. Tell lens agents: "comments containing `Claude Code Review` in their body or attribution are prior automated reviews -- do not re-raise the same findings."

## What we never do

- **Don't post.** review-branch never calls `gh pr comment`, `gh pr review`, `gh api ... -X POST`.
- **Don't merge.** Obviously.
- **Don't fetch check runs / CI status.** Not relevant to the review.
