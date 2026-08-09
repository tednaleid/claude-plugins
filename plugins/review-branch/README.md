# review-branch

Deep, multi-lens code review of an MR, PR, or any local branch. Findings are
structured data rendered into a collaborative HTML tracker served by a local
daemon. Nothing auto-posts; posting happens through companion comment skills
only when explicitly asked.

## What it does

Given an MR number, PR number, MR/PR URL, or branch name, the skill:

1. Auto-detects the VCS from `git remote get-url origin` (gitlab, github, or
   local-only mode).
2. Creates a round directory in the central review store
   (`~/.local/share/review-branch/<repo-id>/<slug>/round-N/`).
3. Sets up an isolated worktree via the worktree plugin.
4. Dispatches 4 parallel lens subagents (architecture, security, coverage,
   naming) that read full source files and run tests.
5. Aggregates findings into `review.toml`: severities, draft comments,
   anchors, plus an explanatory SVG diagram of what the branch does.
6. Renders and serves the tracker: `review-branch open` prints a
   `http://127.0.0.1:43117/...` URL.

In the tracker you toggle Post to MR on the findings you want posted (off by
default), edit the comment drafts directly, and leave free-text notes
("soften this", "mention the follow-up MR"). State persists to disk through
the daemon and every change is committed to a git repo at the review store
root. When you ask
Claude to post, it interprets your notes, rewrites where asked, and posts the
checked comments through the glab-comment or gh-comment skill with the From
Claude attribution marker.

The page has vim-ish keyboard nav (j/k or the arrow keys move a highlighted
finding, space toggles its Post checkbox, Enter folds it and moves on, z
folds it in place, n jumps to its note editor) and every finding can be
collapsed independently; press `?` for the full shortcut list.

## Install

```bash
claude plugin install review-branch@tednaleid
claude plugin install worktree@tednaleid       # recommended companion
```

The skill installs the `review-branch` CLI to `~/.local/bin` on first use
(`review_tool.py install`).

## Use

- `/review-branch 124` (MR or PR number, picked by remote)
- `/review-branch https://github.com/owner/repo/pull/42`
- `/review-branch feature/auth-fix` (diff vs the default branch)
- `/review-branch` (current branch)

Useful CLI verbs against a round directory: `open` (serve and print URL),
`render` (refresh the on-disk snapshot), `status` (merged state as JSON),
`manifest` (postable comments), `stop` (stop the daemon).

## Design notes

- Structured data is canonical: `review.toml` (agent-written) and
  `state.json` (browser-written via the daemon) merge at render and post
  time; your edits win. See `skills/review-branch/references/data-format.md`.
- The daemon serves every review on one port; `GET /` is an index of all
  reviews. See `skills/review-branch/references/http-api.md`.
- Findings are append-only within a round; re-reviews create new rounds;
  comment rewrite history lives in the review store's git log.
- The worktree is left in place; the skill prints the cleanup command.

## Tests

- `just test` runs the fast suite (no browser required).
- `just test-ui` runs a committed Playwright suite against a real `serve`
  daemon, covering the page JS: keyboard nav, fold, click-to-edit, save
  status, and the CSS glyphs. One-time setup:
  `uv run --with pytest-playwright playwright install chromium`.
- `just test-all` runs both.
