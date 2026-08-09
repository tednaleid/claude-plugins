# worktree

Create and manage git worktrees for reviewing an MR/PR or working on a branch in isolation.
The `/worktree` skill drives it for agents (create a worktree, then enter it); the `wt` CLI is
the same script for driving it by hand.

## Create targets

- An **MR number** (GitLab remote, e.g. `124`) -- resolves the source branch via `glab mr view`.
- A **PR number** (GitHub remote) -- resolves via `gh pr view`.
- An **MR or PR URL** -- extracts the number, resolves as above.
- A **branch name** -- uses it directly.
- **Nothing** -- uses the current branch.

Create then:

1. Makes `.claude/worktrees/<slug>` from `origin/<branch>` (or a local branch / HEAD as fallback).
2. Copies gitignored env files (`.env`, `.env.*`, `.envrc`) from the main worktree.
3. Bootstraps via `direnv allow` when the parent `.envrc` was allowed; otherwise `uv sync` /
   `bun install` / `pnpm install` / `npm install` by lock file.
4. Applies any `.worktree.toml` hooks, prints the path on stdout and a summary on stderr.

## Install the plugin (for the `/worktree` skill)

```bash
claude plugin install worktree@tednaleid
```

Invoke with `/worktree <mr-or-pr-or-branch>`, or just describe what you want ("worktree MR 124
for review", "set up a worktree for feature/auth-fix").

## Install the `wt` CLI (to drive it by hand)

From a checkout of this repo:

```bash
plugins/worktree/scripts/worktree_tool.py install   # copies the script to ~/.local/bin/wt
```

Set `WORKTREE_BIN` to install somewhere other than `~/.local/bin`. The installed `wt` is a
snapshot copy that runs through a `uv` shebang, so its dependency-free script resolves with no
extra setup; re-run `wt install` after a plugin bump to refresh it.

```
wt [list] [filter...]      list worktrees (default), optionally filtered
wt create [target]         create + bootstrap a worktree (see targets above)
wt remove [--force] <t>    remove the one worktree matching <t>
wt install                 copy this script to ~/.local/bin/wt
```

`list`/`remove` match by substring against branch and path; `remove` refuses when more than one
worktree matches and never touches the main worktree. Branch deletion stays manual.

Verbs prefix-match, so `wt cr foo` is `wt create foo` and `wt re foo` is `wt remove foo`. Use
`--` to force the rest to be a list filter even when it looks like a verb: `wt -- create`.

## Changing directory

`wt` cannot `cd` your shell (no child process can), so jumping into a worktree stays a shell
function. A minimal fuzzy jumper:

```zsh
wcd () {
  local worktree
  worktree=$(git worktree list | fzf --query="$1" --select-1 --exit-0 | awk '{print $1}')
  [[ -n "$worktree" ]] && cd "$worktree"
}
```

It reads `git worktree list`, so it works for any worktree regardless of how it was made.

## Per-repo hooks

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

`copy`/`symlink` sources are relative to the main worktree; `command` runs inside the new
worktree.
