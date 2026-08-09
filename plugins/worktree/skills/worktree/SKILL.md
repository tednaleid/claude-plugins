---
name: worktree
description: Create a git worktree for reviewing an MR/PR or working on a branch in isolation. Use when the user wants to review a merge request or pull request, check out a branch in a separate worktree, or uses /worktree. Accepts an MR/PR number, an MR/PR URL, or a branch name. Runs the worktree_tool script (creates the worktree under .claude/worktrees/, copies gitignored env files, bootstraps, applies optional .worktree.toml hooks), then switches the session into it.
allowed-tools: Bash(*worktree_tool.py *), Bash(git *), Read
---

# Worktree

Create an isolated git worktree and switch the session into it. The heavy lifting is a
standalone script; this skill runs it and enters the result.

## Workflow

1. **Run the script** from the repo root, passing the target (MR/PR number, MR/PR URL, or
   branch name; omit for the current branch):

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree_tool.py" <target>
   ```

   It resolves the branch, creates the worktree under `.claude/worktrees/<slug>`, copies
   gitignored `.env*`/`.envrc` from the main worktree, bootstraps (direnv when an `.envrc`
   was allowed in the parent, else uv/bun/pnpm/npm by lockfile), applies any
   `.worktree.toml` hooks, and prints the worktree path on stdout with a summary on stderr.

2. **Enter it.** Call the `EnterWorktree` tool (not a Bash command) with `path` set to the
   printed worktree path, so subsequent commands run inside it.

3. **Report** the path and the one-line summary the script emitted.

## Optional per-repo hooks

A `.worktree.toml` at the repo root adds setup beyond the defaults:

```toml
[[copy]]
from = ".env.staging"   # relative to the main worktree
to = ".env"             # relative to the new worktree

[[symlink]]
from = ".bin"
to = ".bin"

[[command]]
run = "just bootstrap"
```

`copy` and `symlink` sources are relative to the main worktree; `command` runs inside the
new worktree. Do not put destructive setup (migrations, resets) in a `command` hook without
the user's say-so.

## Cleanup

When the user is done:

1. `EnterWorktree` with `action: "keep"` to return to the original directory (or just
   `cd` back).
2. `git worktree remove .claude/worktrees/<slug>`
3. If the script created a brand-new local branch (target did not exist anywhere), delete it
   with `git branch -d <branch>` when no longer needed.

## Rules

- The worktree directory is always under `.claude/worktrees/` relative to the repo root.
- Only gitignored `.env*`/`.envrc` are copied. Tracked files are already in the checkout.
- Do not run database migrations or destructive setup without asking.
