---
name: review-branch
description: Deep multi-lens review of an MR, PR, or any local branch. Dispatches 4 parallel subagents (architecture, security, test coverage, naming/API) inside an isolated worktree, aggregates findings with severity tags, and writes a dark-themed HTML disposition tracker (with checkboxes and localStorage) plus copy-paste comment drafts to .llm/reviews/. Nothing auto-posts; the human reviews and posts by hand. Use when asked to deeply review an MR/PR, do a thorough code review of a branch, get a second opinion on changes, or uses /review-branch. Works against GitLab (glab) and GitHub (gh); auto-detects from the git remote. Also handles local-only branch reviews (no MR/PR yet) by diffing against the default branch.
allowed-tools: Bash(git *), Bash(glab *), Bash(gh *), Bash(jq *), Bash(mkdir *), Bash(test *), Bash(ls *), Bash(open *), Read, Write, Edit, Glob, Grep, Agent, Skill
---

# review-branch

Produce a deep, multi-lens code review as a self-contained HTML disposition tracker. Nothing posts to GitLab/GitHub -- the human reviews and copies comments by hand.

## Workflow

```
PARSE INPUT --> DETECT VCS --> RESOLVE BRANCH + SLUG --> WORKTREE --> SEED CONTEXT
            --> DISPATCH 4 LENSES (parallel) --> AGGREGATE --> RENDER HTML --> REPORT
```

## Step 1: Parse input

The skill accepts one optional argument. Determine shape:

| Input | Meaning |
|---|---|
| digits only (e.g., `124`) | MR/PR number -- VCS picked in Step 2 |
| URL containing `/merge_requests/<n>` | GitLab MR; extract `<n>` |
| URL containing `/pull/<n>` | GitHub PR; extract `<n>` |
| anything else | branch name; use directly |
| no argument | use the current branch (`git rev-parse --abbrev-ref HEAD`) |

Error early if:

- Current branch is `main`, `master`, or `trunk` and no argument was given -- there's nothing to review.
- The argument is a number but no remote is detected (Step 2 returns local-only) -- ambiguous, ask the user.

## Step 2: Detect VCS

```bash
remote=$(git remote get-url origin 2>/dev/null || echo "")
case "$remote" in
  *gitlab*) vcs="glab" ;;
  *github*) vcs="gh" ;;
  *)        vcs="local" ;;
esac
```

If `vcs="local"` and the input is a branch name or empty, proceed in **local mode** -- no MR/PR metadata, no prior comments. Diff is against `origin/<default-branch>` (see Step 3).

## Step 3: Resolve branch and slug

### Resolve the source branch and metadata

| Input shape | VCS | Source branch |
|---|---|---|
| MR number | `glab` | `glab mr view <n> --output json \| jq -r .source_branch` |
| PR number | `gh` | `gh pr view <n> --json headRefName --jq .headRefName` |
| branch name | any | the input |
| (none) | any | `git rev-parse --abbrev-ref HEAD` |

Also fetch the target branch:

- MR: `.target_branch` from the same `glab mr view --output json` call.
- PR: `--json baseRefName --jq .baseRefName`.
- Local mode: `git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`.

### Build the slug

- MR mode: `mr-<n>`
- PR mode: `pr-<n>`
- Branch mode: slugify the branch name -- `tr '/' '-' | tr -c 'a-zA-Z0-9-' '-'`. Trim leading/trailing dashes.

### Decide the output filename

Output goes to `.llm/reviews/<slug>-review.html`. Check whether prior reviews exist for this slug:

```bash
mkdir -p .llm/reviews
existing=$(ls .llm/reviews/<slug>-review*.html 2>/dev/null | wc -l | tr -d ' ')
case "$existing" in
  0) out=".llm/reviews/<slug>-review.html" ;;
  *) round=$((existing + 1)); out=".llm/reviews/<slug>-review-${round}.html" ;;
esac
```

The `{{LOCAL_STORAGE_KEY}}` for the HTML is the output basename without `.html`, plus `-checks-v1`. Example: `mr-124-review-2-checks-v1`.

## Step 4: Worktree

The skill operates inside an isolated git worktree of the source branch. Subagents read source files and run tests from there.

**Preferred:** invoke the `worktree` skill via the `Skill` tool with the resolved source branch (or MR/PR number) as input. It handles branch resolution, env-file copy, env bootstrap, and the `EnterWorktree` call.

```
Skill(skill: "worktree", args: "<source-branch-or-mr-pr-number>")
```

**Fallback** (if `worktree` skill isn't available in the user's plugin set): perform the inline equivalent yourself:

```bash
mkdir -p .claude/worktrees
git fetch origin
dir=$(echo "<source-branch>" | tr '/' '-')
git worktree add .claude/worktrees/$dir origin/<source-branch> \
  || git worktree add .claude/worktrees/$dir <source-branch>
# copy gitignored env files (.env*, .envrc) from main worktree
# bootstrap with direnv allow OR uv sync / bun install / pnpm install / npm install
# call EnterWorktree(path: .claude/worktrees/$dir)
```

After this step, your working directory is the worktree. All file reads in subsequent steps use the worktree as the repo root.

## Step 5: Seed context

Build the inputs the lens subagents need. Write them to files in the worktree's `.llm/` (or `/tmp/` if `.llm/` isn't writable) so subagents can read them.

### Diff and changed files

```bash
case "$vcs" in
  glab) glab mr diff <n> > .llm/diff.patch ;;
  gh)   gh pr diff <n>   > .llm/diff.patch ;;
  local) git diff origin/<target-branch>...HEAD > .llm/diff.patch ;;
esac
grep '^diff --git' .llm/diff.patch | awk '{print $4}' | sed 's@^b/@@' > .llm/changed-files.txt
```

### Prior comments (MR/PR mode only)

See `references/glab.md` and `references/gh.md` for the exact commands. The simplest output that lens prompts can consume is the human-readable markdown form:

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

Skip this step in local mode -- there are no prior comments. Note this for the lens prompts ("no prior discussion to consider").

### Hex detection

```bash
hex_doc=""
hex_mode="false"
test -f docs/hexagonal-architecture.md && { hex_doc="docs/hexagonal-architecture.md"; hex_mode="true"; }
test -d core/ports && hex_mode="true"
test -d src/core/ports && hex_mode="true"
```

Pass `hex_mode` and `hex_doc` to the architecture lens prompt.

### Spec detection (optional, helpful)

If the branch name matches a ticket pattern (e.g., `OMNI-15209`, `JIRA-1234`), look for `docs/specs/<TICKET>*.md` or `docs/spec/<TICKET>*.md`. If found, pass the path as `spec_path` to the coverage lens.

```bash
ticket=$(echo "<source-branch>" | grep -oE '[A-Z]+-[0-9]+' | head -1)
[ -n "$ticket" ] && spec=$(ls docs/spec*/${ticket}*.md 2>/dev/null | head -1)
```

## Step 6: Dispatch lenses (parallel)

Use the `Agent` tool to spawn all 4 lens subagents **in a single message** so they run in parallel. Each gets a prompt with the seed context.

```
Agent(
  subagent_type: "review-branch:lens-architecture",
  description: "Architecture lens",
  prompt: """
    worktree_path: <absolute path to worktree>
    target_branch: <e.g., main>
    diff_path: <absolute path to .llm/diff.patch>
    changed_files: <newline-joined list>
    prior_comments_path: <absolute path or 'none' if local mode>
    hex_mode: <true|false>
    hex_doc: <path or empty>
    spec_path: <path or empty>

    Read references/agent-contract.md for the output schema and tone.
    Read this lens's full prompt at agents/lens-architecture.md.
    Return JSON array per the contract.
  """
)
```

Repeat for `lens-security`, `lens-coverage`, `lens-naming`. Send all four `Agent` calls in one assistant turn -- this is the parallel dispatch.

Each subagent returns a JSON array of findings. Parse each one. If a subagent returns malformed JSON, retry once with a clarifying prompt; if it still fails, log the lens as "no findings" and continue.

## Step 7: Aggregate

Combine the four arrays. Dedupe overlapping findings:

- Same `file` + line range within 5 lines + same general topic (≥50% word overlap in the title) -> merge into one entry.
- When merging: pick the highest severity, keep the most specific description, concatenate distinct `draft_comment` bodies, and union the lens labels.

Sort the merged list:

1. Primary: severity (`high` -> `med` -> `low` -> `info`).
2. Secondary: file path (groups findings touching the same file together).
3. Tertiary: line number ascending within a file.

Number them sequentially (`f1`, `f2`, ...) in this final order. The corresponding draft comments get `c1`, `c2`, ... matching the finding numbers they came from.

## Step 8: Render HTML

Read `assets/template.html`. Follow `references/html-template.md` to substitute every `{{...}}` placeholder. Key substitutions:

- `{{TITLE}}` (appears twice -- use `replace_all: true`): `<MR/PR/Branch> review -- <title-or-branch-name>`. E.g. `MR 124 review -- OMNI-15209 per-repo starting refs`.
- `{{SUBTITLE}}`: one-line description. E.g. `Code review notes for <user> to use when commenting on the MR. Author: <author>.`
- `{{META_ROW}}`: spans per `references/html-template.md#meta-row`.
- `{{SUMMARY_GRID}}`: count cards. Always include High and Med (even if 0); include Low/Info only if non-zero.
- `{{OVERALL_BODY}}`: 1-2 paragraphs. Frame the change in plain language; list the headline asks (top 1-3 findings by severity).
- `{{FINDINGS_BODY}}`: every finding rendered as a `<div class="finding ...">` block per template.
- `{{HEX_TABLE_BLOCK}}`: empty string if `hex_mode=false`; otherwise the H2 + table per template.
- `{{COVERAGE_TABLE_BLOCK}}`: always present. Build the surface/covered/gap rows from the coverage lens findings + reading the test files in the diff.
- `{{FILES_TABLE_BLOCK}}`: from the diff's per-file +/- counts; cross-reference finding numbers.
- `{{COMMENTS_BLOCK}}`: `comment-block` div per draft comment, with matching `data-cid` / checkbox `data-id`.
- `{{LOCAL_STORAGE_KEY}}`: derived from output filename per Step 3.

Write the final HTML with `Write` (single call, full file). HTML-escape all user content (`<`, `>`, `&`).

## Step 9: Report

Print to the user:

1. **Absolute path** of the HTML tracker.
2. **Open command** (macOS): `open <absolute-path>`.
3. **Summary line**: counts per severity, e.g., "1 high, 5 medium, 5 low, 3 info -- 14 findings across 12 files."
4. **Worktree cleanup commands** (the user runs these when done):

   ```
   git worktree remove <worktree-path>
   ```

Do not offer to do more. The skill is complete.

## Rules and anti-patterns

- **No auto-posting.** Never call `glab mr note`, `gh pr comment`, or any post/edit endpoint on the MR/PR conversation.
- **No confidence threshold.** Every lens finding lands in the tracker. Severity tags carry the signal; the human dispositions by checking the box.
- **Read full files end-to-end.** The diff is for navigation only. Don't synthesize findings from grep snippets.
- **Reproduce when possible.** Subagents should try to confirm suspected bugs by running tests. `reproduced: true` is a much stronger signal than `reproduced: false`.
- **Worktree stays.** Do not auto-remove it. The user may want to re-run, inspect findings against source, or extend the review manually.
- **One new file per round.** When re-reviewing after the author pushes new commits, write `-review-2.html`, `-review-3.html`, etc. Never overwrite a prior round.
- **Stop after Step 9.** Do not summarize again, do not offer to refine, do not start a new review.
