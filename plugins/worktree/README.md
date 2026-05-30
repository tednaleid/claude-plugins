# worktree

Create an isolated git worktree for reviewing an MR/PR or working on a branch.

The skill accepts:

- An **MR number** (GitLab remote, e.g. `124`) -- resolves the source branch via `glab mr view`.
- A **PR number** (GitHub remote) -- resolves via `gh pr view`.
- An **MR or PR URL** -- extracts the number, resolves as above.
- A **branch name** -- uses it directly.

It then:

1. Creates `.claude/worktrees/<dir>` from `origin/<branch>` (or local branch / HEAD as fallback).
2. Copies gitignored env files (`.env`, `.env.*`, `.envrc`) from the main worktree.
3. Bootstraps via `direnv allow` if `.envrc` is present; otherwise `uv sync` / `bun install` / `pnpm install` / `npm install` based on lock files.
4. Switches the session into the worktree (`EnterWorktree`).

**Cleanup is manual.** When done, the skill prints the cleanup commands (`git worktree remove .claude/worktrees/<dir>` and an optional `git branch -d` for newly created branches).

## Install

```bash
claude plugin install worktree@tednaleid
```

## Use

Invoke with `/worktree <mr-or-pr-or-branch>` or just describe what you want:

- "Worktree MR 124 for review"
- "Set up a worktree for branch feature/auth-fix"
- "Check out PR https://github.com/owner/repo/pull/42 in a worktree"
