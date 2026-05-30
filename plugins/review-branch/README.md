# review-branch

Deep, multi-lens code review of an MR, PR, or any local branch. Produces a self-contained HTML disposition tracker plus draft comments you can copy into the MR/PR by hand. Nothing auto-posts.

## What it does

Given an MR number, PR number, MR/PR URL, or branch name, the skill:

1. **Auto-detects the VCS** from `git remote get-url origin` (`gitlab` -> `glab`, `github` -> `gh`, neither -> local-only mode).
2. **Sets up an isolated worktree** of the branch via the [`worktree`](../worktree/) plugin (or inline fallback).
3. **Fetches prior comments** from the MR/PR so lens agents don't re-raise resolved topics.
4. **Detects whether hexagonal architecture applies** (looks for `docs/hexagonal-architecture.md` or `core/ports/`). If yes, the architecture lens uses a hex-aware prompt; otherwise a general layering/boundaries prompt.
5. **Dispatches 4 parallel subagents** -- one per lens -- inside the worktree so they can read full source files end-to-end and run tests to reproduce suspected bugs:
   - **architecture** (hex compliance OR general layering)
   - **security** (trust boundaries, injection, auth, secrets)
   - **coverage** (test gaps for the new behavior)
   - **naming** (API ergonomics, naming consistency, public surface)
6. **Aggregates findings** -- dedupes overlapping reports across lenses, sorts by severity (high -> med -> low -> info), then by file. No confidence threshold; severity is the signal.
7. **Renders an HTML disposition tracker** at `.llm/reviews/<slug>-review.html`. The tracker has a dark theme, severity-colored finding cards, per-finding checkboxes backed by `localStorage`, summary counts, optional hex-compliance + test-coverage + files-touched tables, and a "Suggested comments (drafts)" section with copy-paste-ready bodies.
8. **Writes a new file per re-review round** (`-review-2.html`, `-review-3.html`, ...) so prior review state is never lost when the author pushes new commits.

## Install

```bash
claude plugin install review-branch@tednaleid
claude plugin install worktree@tednaleid       # recommended companion
```

## Use

Invoke with `/review-branch <target>` or describe what you want:

- `review-branch 124` -- MR or PR number, picks `glab` or `gh` by remote
- `review-branch https://github.com/owner/repo/pull/42`
- `review-branch feature/auth-fix` -- diff vs `origin/<default-branch>`
- `review-branch` -- defaults to the current branch

The skill prints the absolute path of the HTML tracker when finished. Open it (`open .llm/reviews/<slug>-review.html` on macOS), work through the checklist, and copy the drafted comments into the MR/PR.

## Output layout

```
.llm/
└── reviews/
    ├── mr-124-review.html        # GitLab MR
    ├── pr-42-review.html         # GitHub PR
    ├── feature-auth-fix-review.html   # local branch
    └── mr-124-review-2.html      # round 2, after author pushed changes
```

`.llm/` is conventionally gitignored. The skill creates it if missing.

## Design notes

- **No auto-posting.** The HTML and comment drafts are for the human reviewer; the skill never touches the MR/PR conversation.
- **No confidence threshold.** All findings surface with severity tags; the human dispositions by checking the box.
- **Worktree is left in place.** The skill prints the cleanup command when it finishes. Use it if you want to re-run, inspect findings against the source, or extend the review manually.
