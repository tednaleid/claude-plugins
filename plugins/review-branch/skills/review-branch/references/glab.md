# glab cheatsheet for review-branch

`glab` is the GitLab CLI. The skill uses these specific invocations.

## Constraint

**Never use `glab ci view`** -- it crashes when run non-interactively (no TTY). For pipeline data, use `glab api projects/<id>/pipelines/<pid>/jobs` instead. The review-branch skill doesn't need pipeline data.

## MR metadata

```bash
glab mr view <n> --output json
```

Returns the full MR object. Key fields the skill consumes:

- `iid` -- the MR number (same as input)
- `title`, `description`
- `author.username` (and `author.name` if friendlier)
- `source_branch`, `target_branch`
- `web_url` -- direct link for the meta row
- `state` -- `opened`, `merged`, `closed`
- `changes_count`, `user_notes_count`
- `head_pipeline.status` (optional, not used)

Pipe to `jq` to extract just what's needed:

```bash
glab mr view <n> --output json | jq '{iid, title, author: .author.username, source_branch, target_branch, web_url}'
```

## Diff

```bash
glab mr diff <n>
```

Outputs unified diff text. Pass through to the lens subagents as the source of truth for "what changed."

For a structured changed-files list (path + +/- counts):

```bash
glab mr view <n> --output json | jq -r '.changes[] | "\(.new_path)\t+\(.diff | split("\n") | map(select(startswith("+"))) | length)\t-\(.diff | split("\n") | map(select(startswith("-"))) | length)"'
```

That's heavy. Simpler: grep the diff output itself for `^diff --git` lines.

## Prior discussion (the prior-comments seed)

Two surfaces in GitLab:

1. **Notes** (top-level conversational comments): `glab mr view <n> --comments` -- human-readable text.
2. **Discussions** (inline review threads on specific lines): same `--comments` output includes them, but for structured access use the API:

```bash
glab api "projects/$(glab repo view -F json | jq -r .id)/merge_requests/<n>/discussions"
```

Or get the project path URL-encoded if `glab repo view` isn't available:

```bash
PROJECT=$(git remote get-url origin | sed -E 's|.*://||; s|.*:||; s|\.git$||' | jq -Rr @uri)
glab api "projects/${PROJECT}/merge_requests/<n>/discussions"
```

Each discussion has `notes[]` with `body`, `author.username`, `position` (for inline threads -- has `new_path`, `new_line`).

For the seed-context use case, the markdown `--comments` view is usually enough:

```bash
glab mr view <n> --comments > /tmp/mr-<n>-prior-comments.md
```

Pass the file path to the lens prompts as "prior discussion (do not re-raise issues already addressed here)."

## Resolved threads

GitLab marks threads resolved when the author or reviewer ticks the box. The `--comments` view includes both resolved and unresolved. The lens agents should treat resolved threads as "already handled, do not re-raise."

The structured `discussions` API gives `notes[0].resolved: true/false` -- filter to unresolved if needed:

```bash
glab api "projects/${PROJECT}/merge_requests/<n>/discussions" \
  | jq '[.[] | select(.notes[0].resolved == false or .notes[0].resolved == null)]'
```

## Recognize a prior Claude review

If a previous run of review-branch (or the older `/review-mr`) posted comments, they'll have a footer line. The seed prompt should tell lens agents: "comments containing `Claude Code Review` in their body or attribution are prior automated reviews -- do not re-raise the same findings."

## What we never do

- **Don't post.** review-branch never calls `glab mr note`, `glab mr comment`, `glab api ... -X POST`.
- **Don't fetch pipelines or jobs.** Not relevant to the review.
- **Don't merge.** Obviously.
