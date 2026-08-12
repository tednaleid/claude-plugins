---
name: review-branch
description: Deep multi-lens review of an MR, PR, or any local branch. Dispatches 4 parallel subagents (architecture, security, test coverage, naming/API) inside an isolated worktree, writes structured findings to a central review store, and serves a collaborative HTML tracker from a local daemon with a default-off Post toggle per finding, editable comment drafts, and notes to Claude that round-trip so checked comments can be posted via the glab-comment or gh-comment skills when explicitly asked. Use when asked to deeply review an MR/PR, do a thorough code review of a branch, get a second opinion on changes, or uses /review-branch. Works against GitLab (glab) and GitHub (gh); auto-detects from the git remote. Also handles local-only branch reviews (no MR/PR yet) by diffing against the default branch.
allowed-tools: Bash(git *), Bash(glab *), Bash(gh *), Bash(jq *), Bash(mkdir *), Bash(test *), Bash(ls *), Bash(open *), Bash(review-branch *), Bash(*review_tool.py *), Read, Write, Edit, Glob, Grep, Agent, Skill
---

# review-branch

Produce a deep, multi-lens code review as structured data rendered into a
collaborative HTML tracker. Findings live in `review.toml`; the human toggles
which findings to post, edits drafts, and leaves notes in the served page;
posting to the MR/PR happens only through the glab-comment or gh-comment
skills and only when explicitly asked.

## Workflow

```
BOOTSTRAP TOOL --> PARSE INPUT --> DETECT VCS --> RESOLVE BRANCH + INIT ROUND
  --> WORKTREE --> SEED CONTEXT --> DISPATCH 4 LENSES (parallel)
  --> WRITE review.toml --> DIAGRAM --> RENDER + OPEN --> REPORT
```

## Step 0: Bootstrap the tool

```bash
review-branch --version 2>/dev/null
```

If the command is missing or prints a version lower than the plugin's copy
(`"${CLAUDE_PLUGIN_ROOT}/scripts/review_tool.py" --version`), run:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/review_tool.py" install
```

This also installs `glab-comment` and `gh-comment` to `~/.local/bin`, the
scripts the glab-comment and gh-comment skills call to post.

## Step 1: Parse input

The skill accepts one optional argument. Determine shape:

| Input | Meaning |
|---|---|
| digits only (e.g., `124`) | MR/PR number; VCS picked in Step 2 |
| URL containing `/merge_requests/<n>` | GitLab MR; extract `<n>` |
| URL containing `/pull/<n>` | GitHub PR; extract `<n>` |
| anything else | branch name; use directly |
| no argument | use the current branch (`git rev-parse --abbrev-ref HEAD`) |

Error early if:

- Current branch is `main`, `master`, or `trunk` and no argument was given.
- The argument is a number but Step 2 detects no remote; ask the user.

## Step 2: Detect VCS

```bash
remote=$(git remote get-url origin 2>/dev/null || echo "")
case "$remote" in
  *gitlab*) vcs="glab" ;;
  *github*) vcs="gh" ;;
  *)        vcs="local" ;;
esac
```

Local mode: no MR/PR metadata, no prior comments; diff against
`origin/<default-branch>`.

## Step 3: Resolve branch, slug, and round directory

| Input shape | VCS | Source branch |
|---|---|---|
| MR number | `glab` | `glab mr view <n> --output json \| jq -r .source_branch` |
| PR number | `gh` | `gh pr view <n> --json headRefName --jq .headRefName` |
| branch name | any | the input |
| (none) | any | `git rev-parse --abbrev-ref HEAD` |

Target branch: MR `.target_branch`; PR `--json baseRefName`; local
`git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`.

Slug: `mr-<n>`, `pr-<n>`, or the branch name through
`tr '/' '-' | tr -c 'a-zA-Z0-9-' '-'` with leading/trailing dashes trimmed.

Create the round directory and capture its absolute path. `init` resolves the
main repo via `git rev-parse --git-common-dir`, so it works from the main repo or from
inside a worktree:

```bash
REVIEW_DIR=$(review-branch init --slug <slug>)
```

## Step 4: Worktree

Invoke the `worktree` skill via the `Skill` tool with the resolved source
branch (or MR/PR number). It handles branch resolution, env-file copy,
bootstrap, and `EnterWorktree`. Fall back to the inline equivalent from that
skill's documentation only if the skill is unavailable.

## Step 5: Seed context

Ephemeral scratch goes in the worktree's `.llm/` (never in `$REVIEW_DIR`).

```bash
BASE=$(git merge-base "origin/<target-branch>" HEAD)
git diff "$BASE"...HEAD > .llm/diff.patch
grep '^diff --git' .llm/diff.patch | awk '{print $4}' | sed 's@^b/@@' \
  | sort -u > .llm/changed-files.txt
```

`glab mr diff` / `gh pr diff` emit a plain unified diff with no `diff --git`
headers, so parsing them yields an empty file list. The worktree is pinned to
the MR/PR head, so `git diff` produces real headers for glab, gh, and local
alike. Assert the extraction worked: if `.llm/diff.patch` is non-empty but
`.llm/changed-files.txt` is empty, stop and report rather than dispatching
lenses with no file list.

Record the commit provenance so the round is anchored to what it reviewed,
reusing `BASE` from above rather than recomputing the merge-base:

```bash
HEAD_SHA=$(git rev-parse HEAD)
MERGE_BASE=$BASE
```

Write these into `[review]` as `head_sha` and `merge_base` in Step 7.

Prior comments (MR/PR mode only; see `references/glab.md` / `references/gh.md`):

```bash
case "$vcs" in
  glab) glab mr view <n> --comments > .llm/prior-comments.md ;;
  gh)
    OWNER_REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
    {
      gh pr view <n> --comments
      echo
      echo "## Inline review comments"
      gh api "repos/${OWNER_REPO}/pulls/<n>/comments" \
        --jq '.[] | "- @\(.user.login) at \(.path):\(.line // .original_line): \(.body)"'
    } > .llm/prior-comments.md
    ;;
esac
```

Hex detection:

```bash
hex_doc=""; hex_mode="false"
test -f docs/hexagonal-architecture.md && { hex_doc="docs/hexagonal-architecture.md"; hex_mode="true"; }
test -d core/ports && hex_mode="true"
test -d src/core/ports && hex_mode="true"
```

Spec detection: if the branch matches a ticket pattern (`[A-Z]+-[0-9]+`),
look for `docs/spec*/<TICKET>*.md` and pass it to the coverage lens.

## Step 6: Dispatch lenses (parallel)

Spawn all 4 lens subagents in a single message. Each prompt carries:
worktree_path, target_branch, diff_path, changed_files, prior_comments_path
(or `none`), hex_mode, hex_doc, spec_path, and - as ABSOLUTE paths built from
`${CLAUDE_PLUGIN_ROOT}` (see Step 0) -
`contract_path: ${CLAUDE_PLUGIN_ROOT}/skills/review-branch/references/agent-contract.md`
and `lens_prompt_path: ${CLAUDE_PLUGIN_ROOT}/agents/lens-<name>.md`. Do not rely on the
subagent resolving `references/...` relatively; one lens could not find its files
and returned wrong keys. Lenses: `review-branch:lens-architecture`,
`review-branch:lens-security`, `review-branch:lens-coverage`,
`review-branch:lens-naming`.

Validate each returned object against the contract schema. If the JSON is
malformed OR the keys do not match (e.g. `line` instead of `line_range`, a
missing `draft_comment`, an invented field), re-prompt that lens once with the
correct field list; if it still fails, log the lens as "no findings" and continue.

## Step 7: Aggregate into review.toml

Dedupe by topic, not proximity: merge two findings only when their descriptions
name the same defect. Two findings that share a line but describe different
issues stay separate; nearness alone never merges. When merging, keep the
highest severity, the most specific description, concatenated distinct drafts,
and unioned lenses.

Route by severity. `high` and `med` become `[[findings]]` (with `comment`
drafts and `anchor`s). `low` and `info` become `[[minor]]` rows - one line each
(`lens`, `file`, `line`, `note`), no draft, no anchor. Sort findings by severity
(high, med), then file, then line; ids `f1`, `f2`, ... in final order.

Write `$REVIEW_DIR/review.toml` incrementally per `references/data-format.md`:

1. First `Write`: the `[review]` table (including `head_sha` and `merge_base`
   from Step 5), `[overall]`, and any `[[hex]]`, `[[coverage]]`,
   `[[files_touched]]`, `[[minor]]` rows.
2. Then append the globally sorted findings in batches of about five per
   `Edit`. Never emit the whole document in one tool call.

Run `review-branch status "$REVIEW_DIR"` after each five-finding batch: it
parses the TOML and prints the merged view, so a syntax error surfaces while you
still know which batch caused it.

Every finding that warrants an MR/PR comment gets a `comment` draft (tone per
`references/agent-contract.md`) and an `anchor` on a line the diff touches.
Context-only findings get `commentable = false`.

## Step 8: Diagram

Pick the diagram type per `references/diagrams.md`, author the SVG file(s)
into `$REVIEW_DIR`, and add `[[assets]]` entries. Skip only for trivial
branches.

## Step 9: Render and open

```bash
review-branch render "$REVIEW_DIR"
review-branch open "$REVIEW_DIR"
```

`open` prints the review URL. Offer to open it in the browser:
`open <url>` (macOS).

## Step 10: Report

1. The review URL (and the on-disk fallback `$REVIEW_DIR/review.html`).
2. Summary line: counts per severity.
3. How the collaboration works, in one line: toggle Post to MR, edit drafts,
   leave notes; then ask to post and the comment skills take it from there.
4. Worktree cleanup command: `git worktree remove <worktree-path>`.

Stop after this. Do not summarize again or offer to refine.

## After the human reviews (the collaboration loop)

Read state with `review-branch status "$REVIEW_DIR"`. The human's phrasing
picks the mode:

- "update the html for f8": rewrite that finding's `comment` in review.toml
  (start from their `edited_comment` if present), bump `comment_rev`, run
  `review-branch render`, done; the served page reloads itself.
- "show me the edit here": print the revised body in the terminal instead.
- "post the note about X" / "promote that note": promote the `[[minor]]` row
  to a full `[[findings]]` entry. Assign the next `f<N>` id, write a `comment`
  draft (question-based tone) and an `anchor` on a line the diff touches,
  remove the row from `[[minor]]`, then run `review-branch render`. From
  there it posts like any finding.
- "post the checked ones" / `/glab-comment` / `/gh-comment`: interpret notes
  and post through the matching comment skill. A clear note produces a
  rewrite (bump `comment_rev`, record in review.toml). An ambiguous note, one
  contradicting the finding, or one that reads as a question holds that
  finding out of the batch (`--exclude`); post the clear ones and raise the
  held ones for discussion.

  Before building the manifest, compare the current MR/PR head to the round's
  `head_sha`; if it has moved, warn the human that anchors may have shifted and
  ask before posting. `review-branch manifest "$REVIEW_DIR"` emits the
  batch for the comment skill.
- After posting: write `posted_at`, `posted_url`, `posted_body` into
  review.toml, then run `review-branch render`; the render commit sweeps the
  posted fields into history.

## Rules and anti-patterns

- **No auto-posting.** Posting happens only through the glab-comment or
  gh-comment skills, and only when explicitly asked. Never call `glab mr
  note`, `gh pr comment`, or raw discussion/review-comment endpoints.
- **Findings are append-only.** `[[findings]]` (high/med) are never deleted or
  renumbered within a round; a wrong finding just stays off (its Post toggle
  left unchecked). A re-review after new pushes is a new round: `review-branch
  init` again. `[[minor]]` rows are the exception: promoting a minor note
  moves it into `[[findings]]` and removes it from `[[minor]]`.
- **review.toml is yours; state.json is not.** Never write state.json; the
  daemon owns it.
- **Surface by the bar, route by severity.** Lenses surface only what clears the
  contract's bar; high/med land in `[[findings]]`, low/info in `[[minor]]`.
- **Read full files end-to-end.** The diff is for navigation only.
- **Reproduce when possible.** `reproduced: true` is a much stronger signal.
- **Worktree stays.** Do not auto-remove it.
- **Stop after Step 10.**
